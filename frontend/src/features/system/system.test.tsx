import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { STALE_STATUS, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';
import { expectStaleNote } from '../../test/staleNote';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/system', () => {
  it('shows the worker, the evaluator lag, the inboxes, the queues and the build', async () => {
    const status = makeStatus({
      inboxes: [
        { id: 'i1', kind: 'smtp', label: 'Veeam reports', last_message_at: '2026-11-19T23:05:00Z' },
        { id: 'i2', kind: 'webhook', label: 'Script <script>window.__pwned = 1</script> results', last_message_at: null },
      ],
      queue: { pending_messages: 3, pending_notifications: 0, failed_notifications: 0 },
      evaluator_lag_seconds: 75,
      revision: 'abc1234def5678',
    });
    stubFetch({ ...ME, 'GET /api/v1/system/status': { status: 200, body: status } });
    renderApp('/system');
    expect(await screen.findByRole('heading', { level: 1, name: strings.system.title })).toBeTruthy();
    const worker = await screen.findByTestId('worker-state');
    expect(worker.textContent).toContain(strings.system.heartbeatOk);
    expect(worker.querySelector('svg')).toBeTruthy();
    expect(screen.getByText('20 s ago')).toBeTruthy();
    expect(screen.getByText('worker-1:42')).toBeTruthy();
    expect(screen.getByTestId('evaluator-lag').textContent).toBe('75 s behind');
    const inboxes = screen.getByRole('heading', { level: 2, name: strings.system.inboxesTitle }).closest('section') as HTMLElement;
    expect(within(inboxes).getAllByRole('listitem')).toHaveLength(2);
    expect(within(inboxes).getByText('SMTP')).toBeTruthy();
    expect(within(inboxes).getByText(strings.system.noMessageYet)).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
    const queues = screen.getByRole('heading', { level: 2, name: strings.system.queuesTitle }).closest('section') as HTMLElement;
    expect(within(queues).getByText('3')).toBeTruthy();
    expect(screen.getByTestId('system-version').textContent).toBe('27.0.0');
    expect(screen.getByTestId('system-revision').textContent).toBe('abc1234def5678');
    expect(screen.getByText(strings.system.extensionApi)).toBeTruthy();
    expect(screen.queryByTestId('stale-worker-banner')).toBeNull();
  });

  it('renders hostile inbox labels and the worker holder as text, never as markup', async () => {
    const img = '<img src=x onerror="window.__pwned=1">';
    const link = '<a href="javascript:window.__pwned=2">x</a>';
    const holder = `worker-1 ${link}`;
    const base = makeStatus();
    const status = makeStatus({
      worker: { ...base.worker, holder },
      inboxes: [
        { id: 'i1', kind: 'smtp', label: img, last_message_at: null },
        { id: 'i2', kind: 'webhook', label: link, last_message_at: null },
      ],
    });
    stubFetch({ ...ME, 'GET /api/v1/system/status': { status: 200, body: status } });
    const { container } = renderApp('/system');
    const inboxesTitle = await screen.findByRole('heading', { level: 2, name: strings.system.inboxesTitle });
    const inboxes = inboxesTitle.closest('section') as HTMLElement;
    expect(within(inboxes).getByText(img)).toBeTruthy();
    expect(within(inboxes).getByText(link)).toBeTruthy();
    const worker = screen.getByRole('heading', { level: 2, name: strings.system.workerTitle }).closest('section') as HTMLElement;
    expect(within(worker).getByText(holder)).toBeTruthy();
    expect(container.querySelector('script, img[onerror], a[href^="javascript:"]')).toBeNull();
    expect(document.querySelector('script, img[onerror], a[href^="javascript:"]')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it('says the worker is stale, with the banner above, and shows the error state with a retry', async () => {
    stubFetch({ ...ME, 'GET /api/v1/system/status': { status: 200, body: STALE_STATUS } });
    const first = renderApp('/system');
    expect((await screen.findByTestId('worker-state')).textContent).toContain(strings.system.heartbeatStale);
    expect(screen.getByText('21 min ago')).toBeTruthy();
    expect(await screen.findByTestId('stale-worker-banner')).toBeTruthy();
    first.unmount();
    vi.unstubAllGlobals();
    stubFetch({ ...ME, 'GET /api/v1/system/status': { status: 500, body: { title: 'Internal Server Error', status: 500, request_id: 'req-s' } } });
    renderApp('/system');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('req-s');
    expect(within(alert).getByRole('button', { name: strings.states.retry })).toBeTruthy();
  });

  it('keeps the cards on screen when a later refresh fails, with a stale note instead of the error state', async () => {
    let failing = false;
    const { calls } = stubFetch({
      ...ME,
      'GET /api/v1/system/status': () => (failing ? { status: 500, body: { title: 'Internal Server Error', status: 500, request_id: 'req-s2' } } : { status: 200, body: makeStatus() }),
    });
    const start = Date.now();
    renderApp('/system');
    expect(await screen.findByTestId('system-version')).toBeTruthy();
    const asked = () => calls.filter((call) => call.url.includes('/system/status')).length;
    const before = asked();
    failing = true;
    // The status stays fresh for 30 s; a minute on, the page coming back
    // into view refetches it (TanStack Query listens to visibilitychange),
    // like the poll.
    const clock = vi.spyOn(Date, 'now').mockImplementation(() => start + 60_000);
    try {
      await act(async () => {
        window.dispatchEvent(new Event('visibilitychange'));
      });
      await waitFor(() => expect(asked()).toBeGreaterThan(before));
      expectStaleNote(await screen.findByTestId('stale-data'), start);
    } finally {
      clock.mockRestore();
    }
    expect(screen.getByTestId('system-version').textContent).toBe('27.0.0');
    expect(screen.getByTestId('worker-state').textContent).toContain(strings.system.heartbeatOk);
    expect(within(screen.getByRole('main')).queryByRole('alert')).toBeNull();
    expect(screen.queryByText('req-s2')).toBeNull();
    expect(screen.queryByRole('button', { name: strings.states.retry })).toBeNull();
  });

  it('is the same page for the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, 'GET /api/v1/system/status': { status: 200, body: makeStatus() } });
    renderApp('/system');
    expect(await screen.findByTestId('system-version')).toBeTruthy();
  });
});
