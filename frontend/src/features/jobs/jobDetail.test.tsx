import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { HOSTILE_JOB, HOSTILE_NAME, OCCURRENCES, makeClient, makeFlip, makeJob, makeMessageDetail, makeOccurrence, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const CLIENTS = { 'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } } };
const JOB = makeJob({ name: HOSTILE_JOB, client_name: HOSTILE_NAME, state: 'missed', state_since: '2026-11-20T04:30:00Z', last_success_at: '2026-11-18T23:40:00Z', match_key: 'Veeam nightly' });
const RESULT = {
  id: 'r1000000-0000-4000-8000-000000000001',
  job_id: JOB.id,
  client_hint: HOSTILE_NAME,
  job_name: HOSTILE_JOB,
  status: 'failed' as const,
  started_at: '2026-11-19T23:00:00Z',
  finished_at: '2026-11-19T23:30:00Z',
  received_at: '2026-11-19T23:31:00Z',
  raw_message_id: 'm1000000-0000-4000-8000-000000000001',
  run_id: 'run-1',
  details: {},
};
const MESSAGE = makeMessageDetail({ subject: `<b>Failed</b> ${HOSTILE_JOB}`, text: 'Backup job: Veeam nightly\n<script>window.__pwned = 9</script>\n<img src=x onerror="window.__pwned = 10">\n<a href="javascript:window.__pwned = 11">link</a>\nStatus: Failed' });
// A run of yesterday, so the strip has a coloured cell whatever day the
// test runs on; the fixed fixture runs fill the history table.
const YESTERDAY = new Date(Date.now() - 86_400_000);
const RECENT = [makeOccurrence({ scheduled_for: YESTERDAY.toISOString(), deadline: new Date(YESTERDAY.getTime() + 3_600_000).toISOString(), state: 'missed' }), ...OCCURRENCES];

function routes() {
  return {
    ...ME,
    ...STATUS,
    ...CLIENTS,
    [`GET /api/v1/jobs/${JOB.id}`]: { status: 200, body: JOB },
    [`GET /api/v1/jobs/${JOB.id}/occurrences`]: { status: 200, body: { items: RECENT, next_cursor: null } },
    [`GET /api/v1/jobs/${JOB.id}/results`]: { status: 200, body: { items: [RESULT], next_cursor: null } },
    'GET /api/v1/flips': { status: 200, body: { items: [makeFlip(), makeFlip({ id: 'f1000000-0000-4000-8000-000000000002', from_state: 'unknown', to_state: 'ok', reason: 'First verified run', at: '2026-11-10T23:30:00Z' })], next_cursor: null } },
    [`GET /api/v1/messages/${RESULT.raw_message_id}`]: { status: 200, body: MESSAGE },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/jobs/:id', () => {
  it('shows the state, the 30-day strip, the schedule, the history and the latest message as escaped text', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    expect(screen.getByRole('link', { name: HOSTILE_NAME })).toBeTruthy();
    // State card: badge with icon and word, since, last success, not acknowledged.
    const state = screen.getByRole('heading', { level: 2, name: strings.jobDetail.stateTitle }).closest('section') as HTMLElement;
    expect(within(state).getAllByText(strings.badge.missed).length).toBeGreaterThan(0);
    expect(within(state).getByText(strings.jobDetail.notAcknowledged)).toBeTruthy();
    expect(within(state).getByText(/ago\)/)).toBeTruthy();
    // The strip: 30 cells, today marked, the fixture days carry their state.
    const strip = await screen.findByTestId('day-strip');
    expect(strip.querySelectorAll('.co-strip__cell')).toHaveLength(30);
    expect(strip.querySelectorAll('.co-strip__cell--today')).toHaveLength(1);
    expect(strip.querySelectorAll('.co-strip__cell[data-state="missed"]').length).toBeGreaterThanOrEqual(1);
    expect(strip.querySelector('.co-strip__cell[data-state="missed"] svg')).toBeTruthy();
    // Schedule.
    const schedule = screen.getByRole('heading', { level: 2, name: strings.jobDetail.scheduleTitle }).closest('section') as HTMLElement;
    expect(within(schedule).getByText('23:00')).toBeTruthy();
    expect(within(schedule).getByText('Europe/Lisbon')).toBeTruthy();
    expect(within(schedule).getByText('Veeam nightly')).toBeTruthy();
    // History: runs newest first, then the state changes.
    const runs = await screen.findByRole('table', { name: strings.jobDetail.runsTab });
    const rows = within(runs).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(RECENT.length);
    expect(rows[0]?.getAttribute('data-state')).toBe('missed');
    expect(within(runs).getByText('disk full')).toBeTruthy();
    await user.click(screen.getByRole('tab', { name: /State changes/ }));
    const flips = await screen.findByRole('table', { name: strings.jobDetail.flipsTab });
    expect(within(flips).getByText('No result by the deadline')).toBeTruthy();
    expect(within(flips).getByText('First verified run')).toBeTruthy();
    // The latest message: text, never HTML.
    const raw = await screen.findByTestId('job-raw-message');
    expect(raw.textContent).toContain('<script>window.__pwned = 9</script>');
    expect(raw.textContent).toContain('<img src=x onerror=');
    expect(raw.querySelector('script, img, a, b')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    expect(document.querySelector('img[onerror]')).toBeNull();
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    expect(screen.getByRole('link', { name: strings.jobDetail.rawOpen }).getAttribute('href')).toContain(`/messages/${RESULT.raw_message_id}`);
  });

  it('acknowledges from the header and shows the time only, never a name', async () => {
    const user = userEvent.setup();
    let job = JOB;
    const { calls } = stubFetch({
      ...routes(),
      [`GET /api/v1/jobs/${JOB.id}`]: () => ({ status: 200, body: job }),
      [`POST /api/v1/jobs/${JOB.id}/acknowledge`]: () => {
        job = { ...job, acknowledged_at: '2026-11-20T08:05:00Z' };
        return { status: 200, body: job };
      },
    });
    renderApp(`/jobs/${JOB.id}`);
    await user.click(await screen.findByRole('button', { name: strings.dashboard.acknowledge }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/acknowledge'))).toBe(true));
    const ack = await screen.findByTestId('acknowledged-at');
    expect(ack.textContent).toMatch(/2026/);
    expect(screen.getByText(strings.jobDetail.acknowledgedBy)).toBeTruthy();
    expect(screen.queryByText(ADMIN.email)).toBeNull();
    expect(screen.queryByRole('button', { name: strings.dashboard.acknowledge })).toBeNull();
  });

  it('shows the not-found state inside the shell, and the empty strip and message for a job without history', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/jobs/nope': { status: 404, body: { title: 'Job not found', status: 404 } } });
    const first = renderApp('/jobs/nope');
    expect(await screen.findByRole('heading', { level: 1, name: strings.jobDetail.notFoundTitle })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.jobDetail.back })).toBeTruthy();
    expect(screen.getByRole('navigation', { name: strings.nav.primary })).toBeTruthy();
    first.unmount();
    vi.unstubAllGlobals();
    const fresh = makeJob({ state: 'unknown' });
    stubFetch({
      ...ME,
      ...STATUS,
      ...CLIENTS,
      [`GET /api/v1/jobs/${fresh.id}`]: { status: 200, body: fresh },
      [`GET /api/v1/jobs/${fresh.id}/occurrences`]: { status: 200, body: { items: [], next_cursor: null } },
      [`GET /api/v1/jobs/${fresh.id}/results`]: { status: 200, body: { items: [], next_cursor: null } },
      'GET /api/v1/flips': { status: 200, body: { items: [], next_cursor: null } },
    });
    renderApp(`/jobs/${fresh.id}`);
    expect(await screen.findByRole('heading', { level: 3, name: strings.jobDetail.stripEmptyTitle })).toBeTruthy();
    expect(await screen.findByText(strings.jobDetail.rawNone)).toBeTruthy();
    expect(screen.queryByRole('button', { name: strings.dashboard.acknowledge })).toBeNull();
  });

  it('is the same page for the technician, with the jobs list linking to it', async () => {
    stubFetch({ ...routes(), 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, 'GET /api/v1/jobs': { status: 200, body: { items: [JOB], next_cursor: null } } });
    renderApp('/jobs');
    const link = await screen.findByRole('link', { name: HOSTILE_JOB });
    expect(link.getAttribute('href')).toBe(`/jobs/${JOB.id}`);
  });
});
