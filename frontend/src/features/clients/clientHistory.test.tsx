import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fill, formatTime } from '../../lib/format';
import { strings } from '../../strings';
import { makeClient, makeFlip, makeJob, makeRibbon } from '../../test/fixtures';
import { ADMIN, holdFetch, renderApp, stubFetch, type FetchAnswer } from '../../test/render';
import { expectStaleNote } from '../../test/staleNote';
import { saveBlob } from '../shared/download';

// The export would otherwise click a temporary link; the mock records
// whether a download was started at all.
vi.mock('../shared/download', () => ({ saveBlob: vi.fn() }));

const saveBlobMock = vi.mocked(saveBlob);

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const CLIENT = makeClient();
const JOBS = [makeJob(), makeJob({ id: 'j1000000-0000-4000-8000-000000000002', name: 'SQL dump script', kind: 'script' })];
const CLIENT_ROUTE = `GET /api/v1/clients/${CLIENT.id}`;
const EXPORT_ROUTE = `GET /api/v1/clients/${CLIENT.id}/export.csv`;
const CHIPS_QUERY = '(max-width: 639px)';

// A flip whose job is not in the client's job list (archived or deleted):
// the page shows the first 8 characters of its id.
const ORPHAN_JOB_ID = 'e7f6a5b4-0000-4000-8000-00000000abcd';

// Hostile text for the client page: each would create an element (and run
// script) if the page rendered it as HTML.
const HOSTILE_CLIENT = 'Harbourside <script>window.__pwned=1</script> Dental';
const HOSTILE_JOB_NAME = 'Veeam <img src=x onerror="window.__pwned=2"> nightly';
const HOSTILE_TEXT = 'Missed: <a href="javascript:window.__pwned=3">x</a>';
const DANGEROUS = 'script, img[onerror], a[href^="javascript:"]';

function routes(extra: Record<string, FetchAnswer> = {}): Record<string, FetchAnswer> {
  return {
    ...ME,
    [CLIENT_ROUTE]: { status: 200, body: CLIENT },
    'GET /api/v1/jobs': { status: 200, body: { items: JOBS, next_cursor: null } },
    'GET /api/v1/dashboard/ribbon': { status: 200, body: makeRibbon() },
    'GET /api/v1/flips': { status: 200, body: { items: [], next_cursor: null } },
    ...extra,
  };
}

async function openTab(name: string) {
  const user = userEvent.setup();
  // The tabs render once the client has loaded.
  await user.click(await screen.findByRole('tab', { name }));
  return { user, panel: screen.getByRole('tabpanel') };
}

/** Phone width for the chips query only; returns the restore function. */
function phoneWidth(): () => void {
  const original = window.matchMedia;
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: query === CHIPS_QUERY,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  });
  return () => {
    window.matchMedia = original;
  };
}

function windowWords() {
  const { window: night } = makeRibbon();
  return { from: formatTime(night.from), to: formatTime(night.to) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  saveBlobMock.mockClear();
});

describe('/clients/:id Night Ribbon tab', () => {
  it('shows a skeleton while the ribbon loads, then the ribbon', async () => {
    stubFetch(routes());
    const release = holdFetch('/dashboard/ribbon');
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.ribbonTab);
    const skeleton = await within(panel).findByRole('status', { busy: true });
    expect(skeleton.textContent).toContain(strings.states.loading);
    expect(within(panel).queryByTestId('night-ribbon')).toBeNull();
    release();
    expect(await within(screen.getByRole('tabpanel')).findByTestId('night-ribbon')).toBeTruthy();
  });

  it('shows the error with the request id when the ribbon fails, and retries', async () => {
    let attempts = 0;
    stubFetch(
      routes({
        'GET /api/v1/dashboard/ribbon': () => {
          attempts += 1;
          return attempts === 1
            ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The ribbon could not be built.', request_id: 'req-21' } }
            : { status: 200, body: makeRibbon() };
        },
      }),
    );
    renderApp(`/clients/${CLIENT.id}`);
    const { user, panel } = await openTab(strings.clientHistory.ribbonTab);
    const alert = await within(panel).findByRole('alert');
    expect(alert.textContent).toContain('The ribbon could not be built.');
    expect(alert.textContent).toContain('req-21');
    expect(within(panel).queryByTestId('night-ribbon')).toBeNull();
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await within(screen.getByRole('tabpanel')).findByTestId('night-ribbon')).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it('keeps the ribbon on screen when a later refresh fails, with a stale note and no error card', async () => {
    let failing = false;
    const { calls } = stubFetch(
      routes({
        'GET /api/v1/dashboard/ribbon': () =>
          failing ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The ribbon could not be built.', request_id: 'req-22' } } : { status: 200, body: makeRibbon() },
      }),
    );
    const start = Date.now();
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.ribbonTab);
    expect(await within(panel).findByTestId('night-ribbon')).toBeTruthy();
    const asked = () => calls.filter((call) => call.url.includes('/dashboard/ribbon')).length;
    const before = asked();
    failing = true;
    // The page coming back into view refetches the ribbon (TanStack Query
    // listens to visibilitychange), like the minute poll.
    await act(async () => {
      window.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(asked()).toBeGreaterThan(before));
    const current = screen.getByRole('tabpanel');
    expectStaleNote(await within(current).findByTestId('stale-data'), start);
    expect(within(current).getByTestId('night-ribbon')).toBeTruthy();
    expect(within(current).queryByRole('alert')).toBeNull();
    expect(within(current).queryByText('req-22')).toBeNull();
    expect(within(current).queryByRole('button', { name: strings.states.retry })).toBeNull();
  });

  it('shows the empty state when the client has no run in the ribbon window', async () => {
    // Only the other client has runs tonight.
    stubFetch(routes({ 'GET /api/v1/dashboard/ribbon': { status: 200, body: makeRibbon({ clients: makeRibbon().clients.slice(1) }) } }));
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.ribbonTab);
    expect(await within(panel).findByRole('heading', { level: 3, name: strings.clientHistory.ribbonEmptyTitle })).toBeTruthy();
    expect(within(panel).getByText(fill(strings.clientHistory.ribbonEmptyLead, windowWords()))).toBeTruthy();
    expect(within(panel).queryByTestId('night-ribbon')).toBeNull();
    expect(within(panel).queryByText('Northwind Legal (fictional)')).toBeNull();
  });

  it('draws only this client in the ribbon, without the client link', async () => {
    stubFetch(routes());
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.ribbonTab);
    const figure = await within(panel).findByTestId('night-ribbon');
    await waitFor(() => expect(figure.querySelectorAll('.co-nr__row-svg').length).toBe(1));
    // The fixture's client 1 has two jobs with four runs between them.
    expect(figure.getAttribute('aria-label')).toBe(fill(strings.ribbon.labelClient, { client: CLIENT.name, runs: 4, ...windowWords() }));
    expect(within(panel).getByText(fill(strings.dashboard.ribbonLead, windowWords()))).toBeTruthy();
    expect(within(figure).queryAllByRole('link')).toHaveLength(0);
    expect(within(panel).queryByText('Northwind Legal (fictional)')).toBeNull();
  });

  it('shows the runs as chips at phone width', async () => {
    const restore = phoneWidth();
    try {
      stubFetch(routes());
      renderApp(`/clients/${CLIENT.id}`);
      const { panel } = await openTab(strings.clientHistory.ribbonTab);
      const chips = await within(panel).findByTestId('ribbon-chips');
      expect(chips.getAttribute('aria-label')).toBe(fill(strings.ribbon.labelClient, { client: CLIENT.name, runs: 4, ...windowWords() }));
      expect(chips.querySelectorAll('.co-nrc__chip')).toHaveLength(4);
      // One client, so no client heading or link inside the chips.
      expect(within(chips).queryAllByRole('link')).toHaveLength(0);
      expect(within(panel).queryByTestId('night-ribbon')).toBeNull();
    } finally {
      restore();
    }
  });
});

describe('/clients/:id History tab', () => {
  it('shows a skeleton while the state changes load, then the table', async () => {
    stubFetch(routes({ 'GET /api/v1/flips': { status: 200, body: { items: [makeFlip()], next_cursor: null } } }));
    const release = holdFetch('/flips');
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.historyTab);
    const skeleton = await within(panel).findByRole('status', { busy: true });
    expect(skeleton.textContent).toContain(strings.states.loading);
    expect(within(panel).queryByRole('table')).toBeNull();
    release();
    expect(await within(screen.getByRole('tabpanel')).findByRole('table', { name: strings.clientHistory.historyTab })).toBeTruthy();
  });

  it('shows the error with the request id when the state changes fail, and retries', async () => {
    let attempts = 0;
    stubFetch(
      routes({
        'GET /api/v1/flips': () => {
          attempts += 1;
          return attempts === 1
            ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The history could not be read.', request_id: 'req-22' } }
            : { status: 200, body: { items: [makeFlip()], next_cursor: null } };
        },
      }),
    );
    renderApp(`/clients/${CLIENT.id}`);
    const { user, panel } = await openTab(strings.clientHistory.historyTab);
    const alert = await within(panel).findByRole('alert');
    expect(alert.textContent).toContain('The history could not be read.');
    expect(alert.textContent).toContain('req-22');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await within(screen.getByRole('tabpanel')).findByRole('table', { name: strings.clientHistory.historyTab })).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it('shows the empty state when no job of the client changed state', async () => {
    const { calls } = stubFetch(routes());
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.historyTab);
    expect(await within(panel).findByRole('heading', { level: 3, name: strings.clientHistory.flipsEmpty })).toBeTruthy();
    expect(within(panel).getByText(strings.clientHistory.flipsLead)).toBeTruthy();
    expect(within(panel).queryByRole('table')).toBeNull();
    expect(calls.find((call) => call.url.includes('/flips'))?.url).toContain(`client_id=${CLIENT.id}`);
  });

  it('lists the state changes with the job name, and a short id for a job not in the job list', async () => {
    const flips = [
      makeFlip({ id: 'f1000000-0000-4000-8000-000000000001', job_id: JOBS[0]?.id, from_state: 'ok', to_state: 'missed', reason: 'No result by the deadline' }),
      makeFlip({ id: 'f1000000-0000-4000-8000-000000000002', job_id: ORPHAN_JOB_ID, from_state: 'failing', to_state: 'ok', reason: 'Success after a failure', at: '2026-11-19T23:30:00Z' }),
    ];
    stubFetch(routes({ 'GET /api/v1/flips': { status: 200, body: { items: flips, next_cursor: null } } }));
    renderApp(`/clients/${CLIENT.id}`);
    const { panel } = await openTab(strings.clientHistory.historyTab);
    const table = await within(panel).findByRole('table', { name: strings.clientHistory.historyTab });
    for (const column of Object.values(strings.clientHistory.flipColumns)) {
      expect(within(table).getByRole('columnheader', { name: column })).toBeTruthy();
    }
    // The job list may answer after the flips: wait for the name to resolve.
    const known = (await within(table).findByText('Veeam nightly')).closest('tr') as HTMLElement;
    expect(within(known).getByText('No result by the deadline')).toBeTruthy();
    expect(within(known).getByText(strings.badge.verified)).toBeTruthy();
    expect(within(known).getByText(strings.badge.missed)).toBeTruthy();

    const short = within(table).getByText(ORPHAN_JOB_ID.slice(0, 8));
    expect(short.classList.contains('mono')).toBe(true);
    const orphan = short.closest('tr') as HTMLElement;
    expect(within(orphan).getByText('Success after a failure')).toBeTruthy();
    expect(within(orphan).getByText(strings.badge.failed)).toBeTruthy();
    expect(within(orphan).getByText(strings.badge.verified)).toBeTruthy();
    expect(within(table).queryByText(ORPHAN_JOB_ID)).toBeNull();
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(panel).queryByRole('button', { name: strings.common.loadMore })).toBeNull();
  });

  it('loads the next page of state changes with Show more', async () => {
    const { calls } = stubFetch(
      routes({
        'GET /api/v1/flips': (url) =>
          new URL(url, 'http://localhost').searchParams.get('cursor') === 'cur-2'
            ? { status: 200, body: { items: [makeFlip({ id: 'f1000000-0000-4000-8000-000000000003', reason: 'Older change', at: '2026-11-10T04:30:00Z' })], next_cursor: null } }
            : { status: 200, body: { items: [makeFlip({ reason: 'Newest change' })], next_cursor: 'cur-2' } },
      }),
    );
    renderApp(`/clients/${CLIENT.id}`);
    const { user, panel } = await openTab(strings.clientHistory.historyTab);
    const table = await within(panel).findByRole('table', { name: strings.clientHistory.historyTab });
    expect(within(table).getByText('Newest change')).toBeTruthy();
    expect(within(table).queryByText('Older change')).toBeNull();
    await user.click(within(panel).getByRole('button', { name: strings.common.loadMore }));
    expect(await within(table).findByText('Older change')).toBeTruthy();
    expect(within(table).getByText('Newest change')).toBeTruthy();
    await waitFor(() => expect(within(screen.getByRole('tabpanel')).queryByRole('button', { name: strings.common.loadMore })).toBeNull());
    expect(calls.some((call) => call.url.includes('/flips') && call.url.includes('cursor=cur-2'))).toBe(true);
  });
});

describe('/clients/:id history export', () => {
  it('downloads the client history as client-<id>-history.csv', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes({ [EXPORT_ROUTE]: { status: 200, body: 'kind,at\r\n', headers: { 'content-type': 'text/csv; charset=utf-8' } } }));
    renderApp(`/clients/${CLIENT.id}`);
    await screen.findByRole('heading', { level: 1, name: CLIENT.name });
    await user.click(screen.getByRole('button', { name: strings.exports.clientHistory }));
    await waitFor(() => expect(saveBlobMock).toHaveBeenCalledTimes(1));
    expect(saveBlobMock.mock.calls[0]?.[1]).toBe(`client-${CLIENT.id}-history.csv`);
    const title = await screen.findByText(strings.exports.downloaded);
    expect(title.closest('.co-toast')?.className).toContain('co-toast--success');
    expect(calls.some((call) => call.url.includes(`/clients/${CLIENT.id}/export.csv`))).toBe(true);
  });

  it('shows the danger toast with the request id on a 500 and starts no download', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(
      routes({ [EXPORT_ROUTE]: { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The export could not be written.', request_id: 'req-23' } } }),
    );
    renderApp(`/clients/${CLIENT.id}`);
    await screen.findByRole('heading', { level: 1, name: CLIENT.name });
    await user.click(screen.getByRole('button', { name: strings.exports.clientHistory }));
    const title = await screen.findByText(strings.exports.failed);
    const toast = title.closest('.co-toast') as HTMLElement;
    expect(toast.className).toContain('co-toast--danger');
    expect(toast.textContent).toContain('The export could not be written.');
    expect(toast.textContent).toContain('req-23');
    expect(calls.some((call) => call.url.includes(`/clients/${CLIENT.id}/export.csv`))).toBe(true);
    expect(saveBlobMock).not.toHaveBeenCalled();
    expect(screen.queryByText(strings.exports.downloaded)).toBeNull();
    // The button is usable again.
    await waitFor(() => expect((screen.getByRole('button', { name: strings.exports.clientHistory }) as HTMLButtonElement).disabled).toBe(false));
  });

  it('explains a 422 (history too large for one file) and starts no download', async () => {
    const user = userEvent.setup();
    stubFetch(routes({ [EXPORT_ROUTE]: { status: 422, body: { title: 'Too many rows', status: 422, detail: 'The export has more than the row limit.' } } }));
    renderApp(`/clients/${CLIENT.id}`);
    await screen.findByRole('heading', { level: 1, name: CLIENT.name });
    await user.click(screen.getByRole('button', { name: strings.exports.clientHistory }));
    const title = await screen.findByText(strings.exports.failed);
    const toast = title.closest('.co-toast') as HTMLElement;
    expect(toast.className).toContain('co-toast--danger');
    expect(toast.textContent).toContain(strings.exports.tooManyClient);
    expect(toast.textContent).not.toContain('The export has more than the row limit.');
    expect(saveBlobMock).not.toHaveBeenCalled();
  });
});

describe('/clients/:id hostile text', () => {
  it('renders a hostile client name, job name, notes and flip reason as literal text on every tab', async () => {
    const client = makeClient({ name: HOSTILE_CLIENT, notes: HOSTILE_TEXT });
    const jobs = [makeJob({ name: HOSTILE_JOB_NAME, client_name: HOSTILE_CLIENT })];
    const first = makeRibbon().clients[0];
    const ribbon = makeRibbon({
      clients: first ? [{ ...first, name: HOSTILE_CLIENT, jobs: first.jobs.map((job) => ({ ...job, name: HOSTILE_JOB_NAME })) }] : [],
    });
    const flips = [makeFlip({ job_id: jobs[0]?.id, reason: HOSTILE_TEXT })];
    stubFetch(
      routes({
        [CLIENT_ROUTE]: { status: 200, body: client },
        'GET /api/v1/jobs': { status: 200, body: { items: jobs, next_cursor: null } },
        'GET /api/v1/dashboard/ribbon': { status: 200, body: ribbon },
        'GET /api/v1/flips': { status: 200, body: { items: flips, next_cursor: null } },
      }),
    );
    const { container } = renderApp(`/clients/${client.id}`);
    const pwned = () => (window as unknown as { __pwned?: number }).__pwned;

    // Jobs tab: the heading, the notes and the job row.
    expect(await screen.findByRole('heading', { level: 1, name: HOSTILE_CLIENT })).toBeTruthy();
    expect(screen.getByText(HOSTILE_TEXT)).toBeTruthy();
    const jobsTable = await screen.findByRole('table', { name: strings.jobs.tableCaption });
    expect((await within(jobsTable).findAllByText(HOSTILE_JOB_NAME)).length).toBeGreaterThan(0);
    expect(container.querySelector(DANGEROUS)).toBeNull();
    expect(document.querySelector(DANGEROUS)).toBeNull();

    // History tab: the resolved job name and the reason.
    const history = await openTab(strings.clientHistory.historyTab);
    const table = await within(history.panel).findByRole('table', { name: strings.clientHistory.historyTab });
    expect(await within(table).findByText(HOSTILE_JOB_NAME)).toBeTruthy();
    expect(within(table).getByText(HOSTILE_TEXT)).toBeTruthy();
    expect(container.querySelector(DANGEROUS)).toBeNull();

    // Night Ribbon tab: the client and job names inside the drawing.
    await history.user.click(screen.getByRole('tab', { name: strings.clientHistory.ribbonTab }));
    const figure = await within(screen.getByRole('tabpanel')).findByTestId('night-ribbon');
    expect(figure.querySelector('.co-nr__client--plain')?.textContent).toBe(HOSTILE_CLIENT);
    expect(figure.getAttribute('aria-label')).toContain(HOSTILE_CLIENT);
    expect(container.querySelector(DANGEROUS)).toBeNull();
    expect(document.querySelector(DANGEROUS)).toBeNull();
    expect(pwned()).toBeUndefined();
  });
});
