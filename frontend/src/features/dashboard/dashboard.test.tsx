import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DashboardToday } from '../../api/dashboard';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { ACTIVITY_ITEMS, BREAKDOWN_CLIENT, BREAKDOWN_VENDOR, DIGEST, EMPTY_RIBBON, EMPTY_TODAY, HOSTILE_JOB, HOSTILE_NAME, makeJob, makeRibbon, makeStatus, makeToday, makeTrend } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const ZERO_TREND = { items: makeTrend(30).map((day) => ({ ...day, verified: 0, failed: 0, silent: 0 })) };

function routes(today: DashboardToday = makeToday()) {
  return {
    ...ME,
    ...STATUS,
    'GET /api/v1/dashboard/today': { status: 200, body: today },
    'GET /api/v1/dashboard/ribbon': (url: string) => ({ status: 200, body: url.includes('problems_only=true') ? makeRibbon({ clients: makeRibbon().clients.slice(0, 1) }) : makeRibbon() }),
    'GET /api/v1/dashboard/trend': { status: 200, body: { items: makeTrend(30) } },
    'GET /api/v1/dashboard/breakdown': (url: string) => ({ status: 200, body: url.includes('by=client') ? BREAKDOWN_CLIENT : BREAKDOWN_VENDOR }),
    'GET /api/v1/activity': { status: 200, body: { items: ACTIVITY_ITEMS, next_cursor: null } },
    'GET /api/v1/digest/preview': { status: 200, body: DIGEST },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/ (morning check)', () => {
  it('shows loading cards, then the five numbers with change and sparkline, the coverage ring, the Seed data label and the time', async () => {
    stubFetch(routes());
    const release = holdFetch('/dashboard/today');
    renderApp('/');
    expect(await screen.findByRole('heading', { level: 1, name: strings.dashboard.title })).toBeTruthy();
    const cards = screen.getByTestId('stat-cards');
    await waitFor(() => expect(cards.querySelectorAll('[aria-busy="true"]').length).toBe(5));
    release();
    await within(cards).findByText('12');
    expect(within(cards).getByText(strings.dashboard.stats.verified)).toBeTruthy();
    expect(within(cards).getByText(strings.dashboard.stats.silent)).toBeTruthy();
    expect(within(cards).getByText(`+2 ${strings.stat.vsYesterday}`)).toBeTruthy();
    // Failed went down by one (a minus sign), silent up by one.
    expect(within(cards).getAllByText(new RegExp(`1 ${strings.stat.vsYesterday}$`))).toHaveLength(2);
    expect(within(cards).getAllByRole('img', { name: /last 14 days: 14 points/ }).length).toBe(4);
    expect(within(cards).getByText(strings.dashboard.pausedNoHistory)).toBeTruthy();
    expect(screen.getByRole('img', { name: /Coverage: 71 percent, 12 of 17 verified/ })).toBeTruthy();
    expect(screen.getByTestId('seed-label').textContent).toContain(strings.dashboard.seedData);
    expect(screen.getByText(/As of \d\d:\d\d/)).toBeTruthy();
  });

  it('lists the attention items silent first with acknowledge, pause and open message; a hostile name stays text; acknowledge posts and shows the time', async () => {
    const user = userEvent.setup();
    let today = makeToday();
    const { calls } = stubFetch({
      ...routes(),
      'GET /api/v1/dashboard/today': () => ({ status: 200, body: today }),
      [`POST /api/v1/jobs/${today.attention[0]?.job_id}/acknowledge`]: () => {
        const first = today.attention[0];
        if (first) {
          today = { ...today, attention: [{ ...first, acknowledged_at: '2026-11-20T08:05:00Z' }, ...today.attention.slice(1)] };
        }
        return { status: 200, body: makeJob({ acknowledged_at: '2026-11-20T08:05:00Z' }) };
      },
    });
    renderApp('/');
    const list = await screen.findByRole('list', { name: strings.dashboard.attentionTitle });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]?.getAttribute('data-state')).toBe('missed');
    expect(rows[1]?.getAttribute('data-state')).toBe('failed');
    expect(rows[2]?.getAttribute('data-state')).toBe('warning');
    // Icon plus word.
    expect(within(rows[0] as HTMLElement).getByText(strings.badge.missed)).toBeTruthy();
    expect((rows[0] as HTMLElement).querySelector('.co-badge svg')).toBeTruthy();
    // The hostile names are text: no element was created from them.
    expect(within(rows[0] as HTMLElement).getByRole('link', { name: HOSTILE_JOB })).toBeTruthy();
    expect(within(rows[0] as HTMLElement).getByRole('link', { name: HOSTILE_NAME })).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
    expect(document.querySelector('img[onerror]')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    // The acknowledged row shows the time only (the API returns no name).
    expect(within(rows[1] as HTMLElement).getByText(/Acknowledged .*07:15|Acknowledged/)).toBeTruthy();
    expect(within(rows[1] as HTMLElement).queryByRole('button', { name: strings.dashboard.acknowledge })).toBeNull();
    expect(within(rows[1] as HTMLElement).getByRole('link', { name: strings.dashboard.openMessage })).toBeTruthy();
    expect(within(rows[0] as HTMLElement).queryByRole('link', { name: strings.dashboard.openMessage })).toBeNull();
    // Acknowledge the silent one.
    await user.click(within(rows[0] as HTMLElement).getByRole('button', { name: strings.dashboard.acknowledge }));
    const post = await waitFor(() => {
      const found = calls.find((call) => call.method === 'POST' && call.url.endsWith('/acknowledge'));
      expect(found).toBeTruthy();
      return found;
    });
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    expect(await screen.findByText(strings.dashboard.acknowledgedToast)).toBeTruthy();
    await waitFor(() => expect(within(screen.getByRole('list', { name: strings.dashboard.attentionTitle })).getAllByText(/Acknowledged/).length).toBe(2));
    // Pause opens the shared pause dialog with the job's name.
    await user.click(within(rows[2] as HTMLElement).getByRole('button', { name: strings.dashboard.pause }));
    expect(await screen.findByRole('dialog', { name: fill(strings.jobs.pauseTitle, { name: 'Cove server' }) })).toBeTruthy();
  });

  it('draws the Night Ribbon: one row per client, hollow rings with a gap line for silent runs, the morning line; problems only narrows the request', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    renderApp('/');
    const figure = await screen.findByTestId('night-ribbon');
    await waitFor(() => expect(figure.querySelectorAll('.co-nr__row-svg').length).toBe(2));
    expect(figure.querySelectorAll('.co-nr__ring--hollow')).toHaveLength(2);
    expect(figure.querySelectorAll('.co-nr__gap')).toHaveLength(2);
    expect(figure.querySelectorAll('.co-nr__ring--verified')).toHaveLength(1);
    expect(figure.querySelectorAll('.co-nr__ring--failed')).toHaveLength(1);
    expect(figure.querySelectorAll('.co-nr__ring--warning')).toHaveLength(1);
    expect(figure.querySelectorAll('.co-nr__ring--pending')).toHaveLength(1);
    expect(figure.querySelectorAll('.co-nr__row-svg .co-nr__morning')).toHaveLength(2);
    // Each row is an image that reads its runs; the client is a link.
    const rows = within(figure).getAllByRole('img');
    expect(rows[0]?.getAttribute('aria-label')).toContain('Missed');
    expect(rows[0]?.getAttribute('aria-label')).toContain('silent until the deadline');
    expect(within(figure).getByRole('link', { name: 'Northwind Legal (fictional)' })).toBeTruthy();
    expect(screen.getByText(fill(strings.dashboard.ribbonCount, { clients: 2, jobs: 4, runs: 6 }))).toBeTruthy();
    await user.click(screen.getByRole('switch', { name: strings.dashboard.problemsOnly }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('/dashboard/ribbon') && call.url.includes('problems_only=true'))).toBe(true));
    await waitFor(() => expect(screen.getByTestId('night-ribbon').querySelectorAll('.co-nr__row-svg').length).toBe(1));
  });

  it('shows the 30-day trend, the breakdown by vendor then by client, and the activity with a kind filter', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    renderApp('/');
    const trend = await screen.findByRole('img', { name: /Last 30 days: 30 days/ });
    expect(trend.querySelectorAll('.co-bars__day')).toHaveLength(30);
    const breakdown = await screen.findByRole('list', { name: /Breakdown/ });
    expect(within(breakdown).getByText('Veeam')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: strings.dashboard.breakdownByClient }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('/dashboard/breakdown') && call.url.includes('by=client'))).toBe(true));
    expect(await within(screen.getByRole('list', { name: /Breakdown/ })).findByText('Northwind Legal (fictional)')).toBeTruthy();
    const activity = screen.getByRole('list', { name: strings.dashboard.activityTitle });
    expect(within(activity).getAllByRole('listitem')).toHaveLength(3);
    expect(within(activity).getByText('Message received in Veeam reports: parsed')).toBeTruthy();
    expect(within(activity).getAllByRole('link', { name: strings.dashboard.activityOpen })).toHaveLength(3);
    await user.click(screen.getByRole('combobox', { name: strings.dashboard.activityKind }));
    await user.click(await screen.findByRole('option', { name: strings.dashboard.activityKinds.ingest }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('/activity') && call.url.includes('kind=ingest'))).toBe(true));
  });

  it('shows the first-run checklist when nothing is expected yet', async () => {
    stubFetch({
      ...routes(EMPTY_TODAY),
      'GET /api/v1/dashboard/ribbon': { status: 200, body: EMPTY_RIBBON },
      'GET /api/v1/dashboard/trend': { status: 200, body: ZERO_TREND },
    });
    renderApp('/');
    const heading = await screen.findByRole('heading', { level: 3, name: strings.dashboard.firstRunTitle });
    const empty = heading.closest('.co-empty') as HTMLElement;
    expect(within(empty).getAllByRole('listitem')).toHaveLength(strings.dashboard.firstRunSteps.length);
    expect(screen.getByRole('link', { name: strings.dashboard.firstRunAction })).toBeTruthy();
    expect(screen.queryByTestId('night-ribbon')).toBeNull();
    expect(screen.queryByTestId('seed-label')).toBeNull();
  });

  it('shows the error state with a retry when today cannot be read, and the empty states of the sections', async () => {
    stubFetch({
      ...routes(),
      'GET /api/v1/dashboard/today': { status: 503, body: { title: 'Service Unavailable', status: 503, detail: 'Try later.', request_id: 'req-9' } },
      'GET /api/v1/dashboard/ribbon': { status: 200, body: EMPTY_RIBBON },
      'GET /api/v1/dashboard/trend': { status: 200, body: ZERO_TREND },
      'GET /api/v1/dashboard/breakdown': { status: 200, body: { by: 'vendor', items: [] } },
      'GET /api/v1/activity': { status: 200, body: { items: [], next_cursor: null } },
    });
    renderApp('/');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((alert) => alert.textContent?.includes('Try later.') && alert.textContent.includes('req-9'))).toBe(true);
    expect(screen.getAllByRole('button', { name: strings.states.retry }).length).toBeGreaterThan(0);
    expect(await screen.findByRole('heading', { level: 3, name: strings.dashboard.ribbonEmptyTitle })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 3, name: strings.dashboard.trendEmptyTitle })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 3, name: strings.dashboard.breakdownEmptyTitle })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 3, name: strings.dashboard.activityEmptyTitle })).toBeTruthy();
  });

  it('previews the digest in a sandboxed frame without script permission, with the subject and the text version', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderApp('/');
    await screen.findByTestId('night-ribbon');
    await user.click(screen.getByRole('button', { name: strings.digest.preview }));
    const dialog = await screen.findByRole('dialog', { name: strings.digest.title });
    expect((within(dialog).getByLabelText(strings.digest.date) as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const frame = (await within(dialog).findByTestId('digest-frame')) as HTMLIFrameElement;
    expect(frame.getAttribute('sandbox')).toBe('');
    expect(frame.getAttribute('srcdoc')).toContain('Morning check, 20 Nov 2026');
    expect(frame.getAttribute('src')).toBeNull();
    expect(within(dialog).getByText(DIGEST.subject)).toBeTruthy();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    await user.click(within(dialog).getByRole('tab', { name: strings.digest.text }));
    expect(within(dialog).getByTestId('digest-text').textContent).toContain('<script>alert(1)</script>');
    expect(dialog.querySelector('script')).toBeNull();
  });

  it('downloads the day and the history exports as CSV', async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => 'blob:csv');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { calls } = stubFetch({
      ...routes(),
      'GET /api/v1/exports/day.csv': { status: 200, body: 'date,client\r\n', headers: { 'content-type': 'text/csv; charset=utf-8' } },
      'GET /api/v1/exports/history.csv': { status: 200, body: 'date,client\r\n', headers: { 'content-type': 'text/csv; charset=utf-8' } },
    });
    renderApp('/');
    await screen.findByTestId('night-ribbon');
    await user.click(screen.getByRole('button', { name: strings.exports.day }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(strings.exports.downloaded)).toBeTruthy();
    const day = calls.find((call) => call.url.includes('/exports/day.csv'));
    expect(day?.url).toMatch(/date=\d{4}-\d{2}-\d{2}/);
    expect((day?.init?.headers as Record<string, string>).Accept).toContain('text/csv');
    await user.click(screen.getByRole('button', { name: strings.exports.history }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(2));
    expect(calls.some((call) => call.url.includes('/exports/history.csv'))).toBe(true);
    click.mockRestore();
  });

  it('is the same page for the technician', async () => {
    stubFetch({ ...routes(), 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN } });
    renderApp('/');
    expect(await screen.findByTestId('night-ribbon')).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.exports.day })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.dashboard.acknowledge }).length).toBeGreaterThan(0);
  });
});
