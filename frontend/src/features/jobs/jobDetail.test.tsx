import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { HOSTILE_JOB, HOSTILE_NAME, OCCURRENCES, makeClient, makeFlip, makeJob, makeMessageDetail, makeOccurrence, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';
import { expectStaleNote } from '../../test/staleNote';

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

const DB_DOWN = 'The database did not answer in time.';
function serverError(requestId: string) {
  return { status: 500, body: { title: 'Internal Server Error', status: 500, detail: DB_DOWN, request_id: requestId } };
}

/** The card (section) under a level-2 heading of the page. */
function card(name: string): HTMLElement {
  return screen.getByRole('heading', { level: 2, name }).closest('section') as HTMLElement;
}

/** GETs of the job itself (not its occurrences, results or flips). */
function jobGets(calls: readonly { readonly method: string; readonly url: string }[]): number {
  return calls.filter((call) => call.method === 'GET' && new URL(call.url, 'http://localhost').pathname === `/api/v1/jobs/${JOB.id}`).length;
}

/** Lets settled fetches land in the queries and render. */
async function settle(ms = 50) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
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

  it('acknowledges from the header and shows the time and the acknowledger', async () => {
    const user = userEvent.setup();
    let job = JOB;
    const { calls } = stubFetch({
      ...routes(),
      [`GET /api/v1/jobs/${JOB.id}`]: () => ({ status: 200, body: job }),
      [`POST /api/v1/jobs/${JOB.id}/acknowledge`]: () => {
        job = { ...job, acknowledged_at: '2026-11-20T08:05:00Z', acknowledged_by: { id: ADMIN.id, email: ADMIN.email } };
        return { status: 200, body: job };
      },
    });
    renderApp(`/jobs/${JOB.id}`);
    await user.click(await screen.findByRole('button', { name: strings.dashboard.acknowledge }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/acknowledge'))).toBe(true));
    const ack = await screen.findByTestId('acknowledged-at');
    // The state card formats acknowledged_at with formatDateTime (the icon has no text).
    expect(ack.textContent).toBe(formatDateTime('2026-11-20T08:05:00Z'));
    // C9-B carry-over: the acknowledger's address sits next to the time.
    expect(screen.getByTestId('acknowledged-by').textContent).toBe(fill(strings.jobDetail.acknowledgedBy, { email: ADMIN.email }));
    expect(screen.getByTestId('acknowledged-by').textContent).toContain(ADMIN.email);
    expect(screen.queryByRole('button', { name: strings.dashboard.acknowledge })).toBeNull();
  });

  it('says an API token acknowledged, without an address', async () => {
    const job = { ...JOB, acknowledged_at: '2026-11-20T08:05:00Z', acknowledged_by: { id: 'u1000000-0000-4000-8000-000000000009', email: null } };
    stubFetch({ ...routes(), [`GET /api/v1/jobs/${JOB.id}`]: { status: 200, body: job } });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByTestId('acknowledged-by')).toBeTruthy();
    expect(screen.getByTestId('acknowledged-by').textContent).toBe(strings.jobDetail.acknowledgedByToken);
    expect(within(screen.getByRole('main')).queryByText(ADMIN.email)).toBeNull();
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

  it('shows a skeleton under the back link while the job loads', async () => {
    stubFetch(routes());
    const release = holdFetch(`/jobs/${JOB.id}`);
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('link', { name: strings.jobDetail.back })).toBeTruthy();
    const main = screen.getByRole('main');
    const busy = within(main).getAllByRole('status', { busy: true });
    expect(busy.length).toBeGreaterThan(0);
    expect(busy.some((node) => node.textContent?.includes(strings.states.loading))).toBe(true);
    expect(within(main).queryByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeNull();
    expect(within(main).queryByRole('alert')).toBeNull();
    release();
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
  });

  it('shows the error state with the request id and a retry when the job fails to load (not a 404), and loads on retry', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch({
      ...routes(),
      // useJob retries a non-404 once, so both first answers fail.
      [`GET /api/v1/jobs/${JOB.id}`]: () => {
        attempts += 1;
        return attempts <= 2 ? serverError('req-job') : { status: 200, body: JOB };
      },
    });
    renderApp(`/jobs/${JOB.id}`);
    const alert = await screen.findByRole('alert', {}, { timeout: 4000 });
    expect(alert.textContent).toContain(DB_DOWN);
    expect(alert.textContent).toContain('req-job');
    expect(attempts).toBe(2);
    expect(screen.getByRole('heading', { level: 1, name: strings.jobs.title })).toBeTruthy();
    expect(screen.queryByRole('heading', { level: 1, name: strings.jobDetail.notFoundTitle })).toBeNull();
    expect(screen.getByRole('link', { name: strings.jobDetail.back })).toBeTruthy();
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    expect(attempts).toBe(3);
  });

  it('keeps the job on screen when a later refetch of it fails, with a stale note', async () => {
    let failJob = false;
    const { calls } = stubFetch({
      ...routes(),
      [`GET /api/v1/jobs/${JOB.id}`]: () => (failJob ? serverError('req-poll') : { status: 200, body: JOB }),
    });
    const start = Date.now();
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    await screen.findByTestId('day-strip');
    expect(screen.queryByTestId('stale-data')).toBeNull();
    failJob = true;
    const before = jobGets(calls);
    // A visibility change refetches the stale queries (the test client keeps
    // refetchOnWindowFocus on with staleTime 0): it stands in for the 60 s
    // poll without fake timers.
    act(() => {
      window.dispatchEvent(new Event('visibilitychange'));
    });
    // The refetch and useJob's one retry (about 1 s later) both fail.
    await waitFor(() => expect(jobGets(calls)).toBeGreaterThanOrEqual(before + 2), { timeout: 4000 });
    await settle();
    expect(screen.getByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    expect(screen.getByTestId('day-strip')).toBeTruthy();
    expect(within(screen.getByRole('main')).queryByRole('alert')).toBeNull();
    expect(screen.queryByText('req-poll')).toBeNull();
    expectStaleNote(await screen.findByTestId('stale-data'), start);
  });

  it('keeps the job on screen when its runs fail to load: the strip and the runs tab show the error with a retry', async () => {
    stubFetch({ ...routes(), [`GET /api/v1/jobs/${JOB.id}/occurrences`]: serverError('req-occ') });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    const strip = await within(card(strings.jobDetail.stripTitle)).findByRole('alert');
    expect(strip.textContent).toContain('req-occ');
    expect(within(strip).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    expect(screen.queryByTestId('day-strip')).toBeNull();
    const runs = await within(card(strings.jobDetail.historyTitle)).findByRole('alert');
    expect(runs.textContent).toContain('req-occ');
    expect(within(runs).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    expect(screen.queryByRole('table', { name: strings.jobDetail.runsTab })).toBeNull();
    // The rest of the page is unaffected.
    expect(card(strings.jobDetail.stateTitle)).toBeTruthy();
    expect(await screen.findByTestId('job-raw-message')).toBeTruthy();
  });

  it('shows the error with a retry in the state changes tab when the flips fail to load', async () => {
    const user = userEvent.setup();
    stubFetch({ ...routes(), 'GET /api/v1/flips': serverError('req-flips') });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('table', { name: strings.jobDetail.runsTab })).toBeTruthy();
    await user.click(screen.getByRole('tab', { name: /State changes/ }));
    const flips = await within(card(strings.jobDetail.historyTitle)).findByRole('alert');
    expect(flips.textContent).toContain('req-flips');
    expect(within(flips).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    expect(screen.queryByRole('table', { name: strings.jobDetail.flipsTab })).toBeNull();
    expect(screen.getByTestId('day-strip')).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
  });

  it('shows the error with a retry in the latest message card when the results fail to load', async () => {
    const { calls } = stubFetch({ ...routes(), [`GET /api/v1/jobs/${JOB.id}/results`]: serverError('req-res') });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    const alert = await within(card(strings.jobDetail.rawTitle)).findByRole('alert');
    expect(alert.textContent).toContain('req-res');
    expect(within(alert).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    expect(screen.queryByTestId('job-raw-message')).toBeNull();
    expect(calls.some((call) => call.url.includes('/messages/'))).toBe(false);
    expect(await screen.findByTestId('day-strip')).toBeTruthy();
  });

  it('shows the error with a retry when the latest message fails with a 500', async () => {
    stubFetch({ ...routes(), [`GET /api/v1/messages/${RESULT.raw_message_id}`]: serverError('req-raw') });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    // useRawMessage retries a non-404 once (about 1 s) before the error shows.
    const alert = await within(card(strings.jobDetail.rawTitle)).findByRole('alert', {}, { timeout: 4000 });
    expect(alert.textContent).toContain('req-raw');
    expect(within(alert).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    expect(within(card(strings.jobDetail.rawTitle)).queryByText(strings.jobDetail.rawGone)).toBeNull();
    expect(screen.queryByTestId('job-raw-message')).toBeNull();
  });

  it('says the latest message was purged when it answers 404, without retrying it', async () => {
    const { calls } = stubFetch({ ...routes(), [`GET /api/v1/messages/${RESULT.raw_message_id}`]: { status: 404, body: { title: 'Message not found', status: 404 } } });
    renderApp(`/jobs/${JOB.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_JOB })).toBeTruthy();
    expect(await within(card(strings.jobDetail.rawTitle)).findByText(strings.jobDetail.rawGone)).toBeTruthy();
    expect(within(card(strings.jobDetail.rawTitle)).queryByRole('alert')).toBeNull();
    expect(screen.queryByTestId('job-raw-message')).toBeNull();
    // A retry would come about 1 s after the first answer.
    await settle(1200);
    expect(calls.filter((call) => call.url.includes(`/messages/${RESULT.raw_message_id}`))).toHaveLength(1);
  });

  it('is the same page for the technician, with the jobs list linking to it', async () => {
    stubFetch({ ...routes(), 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, 'GET /api/v1/jobs': { status: 200, body: { items: [JOB], next_cursor: null } } });
    renderApp('/jobs');
    const link = await screen.findByRole('link', { name: HOSTILE_JOB });
    expect(link.getAttribute('href')).toBe(`/jobs/${JOB.id}`);
  });
});
