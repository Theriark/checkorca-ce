import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getCsrfToken } from '../api/client';
import { Providers } from '../test/Providers';
import { ADMIN, UNAUTHENTICATED, stubFetch } from '../test/render';
import { useAuth } from './useAuth';

function Probe() {
  const { status, user, error, signIn, signOut } = useAuth();
  return (
    <div>
      <output data-testid="status">{status}</output>
      <output data-testid="email">{user?.email ?? ''}</output>
      <output data-testid="error">{error?.status ?? ''}</output>
      <button onClick={() => void signIn({ email: ADMIN.email, password: 'secret-password-1' }).catch(() => undefined)}>
        sign in
      </button>
      <button onClick={() => void signOut()}>sign out</button>
    </div>
  );
}

describe('AuthProvider', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is anonymous after a 401 from /auth/me, then signed in after login, with the CSRF token kept for the client', async () => {
    const { calls } = stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'POST /api/v1/auth/login': { status: 200, body: { user: { ...ADMIN, disabled: false, locked_until: null, created_at: '2026-11-18T00:00:00Z' }, csrf_token: 'csrf-login' } },
      'POST /api/v1/auth/logout': { status: 204 },
    });
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    expect(screen.getByTestId('status').textContent).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anonymous'));
    expect(getCsrfToken()).toBeNull();

    await act(async () => {
      screen.getByText('sign in').click();
    });
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('signed-in'));
    expect(screen.getByTestId('email').textContent).toBe(ADMIN.email);
    expect(getCsrfToken()).toBe('csrf-login');

    await act(async () => {
      screen.getByText('sign out').click();
    });
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anonymous'));
    const logout = calls.find((call) => call.url.endsWith('/auth/logout'));
    expect((logout?.init?.headers as Headers).get('X-CSRF-Token')).toBe('csrf-login');
    expect(getCsrfToken()).toBeNull();
  });

  it('is signed in when /auth/me answers 200', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('signed-in'));
    expect(getCsrfToken()).toBe(ADMIN.csrf_token);
  });

  it('reports an error (not anonymous) when the session lookup fails with 500', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 500, body: { title: 'Internal Server Error', status: 500 } } });
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('error'));
    expect(screen.getByTestId('error').textContent).toBe('500');
  });
});
