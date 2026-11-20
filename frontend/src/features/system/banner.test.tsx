import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { STALE_STATUS, makeClient, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';
import { staleMinutes } from './stale';

const CLIENTS = { 'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('stale-heartbeat banner', () => {
  it('shows a red alert on a signed-in screen when system/status says the worker is stale, with the minutes and the last heartbeat', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN }, ...CLIENTS, 'GET /api/v1/system/status': { status: 200, body: STALE_STATUS } });
    renderApp('/clients');
    const banner = await screen.findByTestId('stale-worker-banner');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.textContent).toContain(strings.worker.staleTitle);
    expect(banner.textContent).toContain('No heartbeat for 21 minutes.');
    expect(banner.textContent).toContain('Last heartbeat');
    expect(banner.querySelector('svg')).toBeTruthy();
  });

  it('shows nothing while the worker ticks, when the status cannot be read, or for an anonymous visitor', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, ...CLIENTS, 'GET /api/v1/system/status': { status: 200, body: makeStatus() } });
    const healthy = renderApp('/clients');
    await screen.findByText('Harbourside Dental (fictional)');
    expect(screen.queryByTestId('stale-worker-banner')).toBeNull();
    healthy.unmount();
    vi.unstubAllGlobals();

    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN }, ...CLIENTS, 'GET /api/v1/system/status': { status: 500, body: { title: 'Internal Server Error', status: 500 } } });
    const broken = renderApp('/clients');
    await screen.findByText('Harbourside Dental (fictional)');
    await waitFor(() => expect(screen.queryByTestId('stale-worker-banner')).toBeNull());
    broken.unmount();
    vi.unstubAllGlobals();

    const { calls } = stubFetch({ 'GET /api/v1/auth/me': { status: 401, body: { title: 'Unauthorized', status: 401 } } });
    renderApp('/login');
    await screen.findByRole('heading', { level: 1, name: strings.login.title });
    expect(calls.some((call) => call.url.includes('/system/status'))).toBe(false);
  });

  it('says the worker never reported when there is no heartbeat at all', async () => {
    stubFetch({
      'GET /api/v1/auth/me': { status: 200, body: ADMIN },
      ...CLIENTS,
      'GET /api/v1/system/status': { status: 200, body: makeStatus({ worker: { heartbeat_at: null, age_seconds: null, stale: true, holder: null, started_at: null } }) },
    });
    renderApp('/clients');
    expect((await screen.findByTestId('stale-worker-banner')).textContent).toContain(strings.worker.staleNever);
  });

  it('rounds the age down to whole minutes, at least one', () => {
    expect(staleMinutes(null)).toBe(0);
    expect(staleMinutes(30)).toBe(1);
    expect(staleMinutes(1260)).toBe(21);
  });
});
