import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { STALE_STATUS, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';

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

  it('is the same page for the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, 'GET /api/v1/system/status': { status: 200, body: makeStatus() } });
    renderApp('/system');
    expect(await screen.findByTestId('system-version')).toBeTruthy();
  });
});
