import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Puzzle } from 'lucide-react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import { PRODUCT_NAME, strings } from '../strings';
import { ADMIN, TECHNICIAN, UNAUTHENTICATED, renderApp, stubFetch } from '../test/render';
import { firstRunValidation, loginErrorMessage } from './authMessages';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('login page', () => {
  it('shows the stacked logo, the form and the version while anonymous', async () => {
    stubFetch({ 'GET /api/v1/auth/me': UNAUTHENTICATED });
    renderApp('/login');
    expect(await screen.findByRole('heading', { level: 1, name: strings.login.title })).toBeTruthy();
    const logo = screen.getByRole('img', { name: PRODUCT_NAME });
    expect(logo.getAttribute('src')).toBe('/brand/logo-stacked-400x400.png');
    expect(screen.getByLabelText(strings.login.email)).toBeTruthy();
    expect(screen.getByLabelText(strings.login.password)).toBeTruthy();
    expect(screen.getByText('27.0.0')).toBeTruthy();
  });

  it('asks for both fields before sending anything', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({ 'GET /api/v1/auth/me': UNAUTHENTICATED });
    renderApp('/login');
    await user.click(await screen.findByRole('button', { name: strings.login.submit }));
    expect(screen.getByRole('alert').textContent).toContain(strings.login.required);
    expect(calls.filter((call) => call.url.endsWith('/auth/login'))).toHaveLength(0);
  });

  it('maps 401, 423, 429 and a network failure to one sentence each', () => {
    expect(loginErrorMessage(new ApiError({ title: 'x', status: 401 }))).toBe(strings.login.wrongCredentials);
    expect(loginErrorMessage(new ApiError({ title: 'x', status: 423 }))).toBe(strings.login.locked);
    expect(loginErrorMessage(new ApiError({ title: 'x', status: 429 }))).toBe(strings.login.tooMany);
    expect(loginErrorMessage(new ApiError({ title: 'x', status: 0 }))).toBe(strings.login.offline);
    expect(loginErrorMessage(new ApiError({ title: 'x', status: 500, detail: 'boom' }))).toBe('boom');
  });

  it('shows the wrong-credentials message after a 401 and keeps the form usable', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'POST /api/v1/auth/login': { status: 401, body: { title: 'Unauthorized', status: 401, request_id: 'req-a' } },
    });
    renderApp('/login');
    await user.type(await screen.findByLabelText(strings.login.email), ADMIN.email);
    await user.type(screen.getByLabelText(strings.login.password), 'wrong-password-1');
    await user.click(screen.getByRole('button', { name: strings.login.submit }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(strings.login.wrongCredentials);
    expect(alert.textContent).not.toContain('req-a');
    expect(screen.getByRole('button', { name: strings.login.submit }).hasAttribute('disabled')).toBe(false);
  });

  it('signs in and lands on the morning check in the shell', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'POST /api/v1/auth/login': {
        status: 200,
        body: { user: { ...ADMIN, disabled: false, locked_until: null, created_at: '2026-11-18T00:00:00Z' }, csrf_token: 'c' },
      },
    });
    const { history } = renderApp('/login');
    await user.type(await screen.findByLabelText(strings.login.email), ADMIN.email);
    await user.type(screen.getByLabelText(strings.login.password), 'correct-password-1');
    await user.click(screen.getByRole('button', { name: strings.login.submit }));
    await waitFor(() => expect(history.location.pathname).toBe('/'));
    expect(await screen.findByRole('navigation', { name: strings.nav.primary })).toBeTruthy();
    expect(screen.getByRole('navigation', { name: strings.nav.quick })).toBeTruthy();
  });

  it('sends a signed-in visitor to the morning check', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    const { history } = renderApp('/login');
    await waitFor(() => expect(history.location.pathname).toBe('/'));
  });

  it('toggles the password visibility', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/v1/auth/me': UNAUTHENTICATED });
    renderApp('/login');
    const password = await screen.findByLabelText(strings.login.password);
    expect(password.getAttribute('type')).toBe('password');
    await user.click(screen.getByRole('button', { name: strings.login.showPassword }));
    expect(password.getAttribute('type')).toBe('text');
  });
});

describe('shell', () => {
  it('sends an anonymous visitor to /login with the path to come back to', async () => {
    stubFetch({ 'GET /api/v1/auth/me': UNAUTHENTICATED });
    const { history } = renderApp('/jobs');
    await waitFor(() => expect(history.location.pathname).toBe('/login'));
    expect(history.location.search).toContain('redirect');
  });

  it('shows every section to the admin, including Settings, and the user menu', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: strings.nav.primary });
    expect(within(nav).getByRole('link', { name: strings.nav.settings })).toBeTruthy();
    expect(within(nav).getByRole('link', { name: strings.nav.morningCheck }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('button', { name: new RegExp(ADMIN.email) })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: strings.nav.morningCheck })).toBeTruthy();
    const logo = screen.getByRole('img', { name: PRODUCT_NAME });
    expect(logo.getAttribute('srcset')).toContain('logo-horizontal-1200x400.png 2x');
  });

  it('hides Settings from the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN } });
    renderApp('/clients');
    const nav = await screen.findByRole('navigation', { name: strings.nav.primary });
    expect(within(nav).queryByRole('link', { name: strings.nav.settings })).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: strings.nav.clients })).toBeTruthy();
    expect(screen.getByText(new RegExp(`${strings.placeholder.arrives} C3`))).toBeTruthy();
  });

  it('opens the command search with Ctrl K and navigates', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    const { history } = renderApp('/');
    await screen.findByRole('navigation', { name: strings.nav.primary });
    await user.keyboard('{Control>}k{/Control}');
    const input = await screen.findByRole('combobox', { name: strings.search.label });
    await user.type(input, 'jobs');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(history.location.pathname).toBe('/jobs'));
  });

  it('renders a plugin route and menu entry', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    renderApp('/reports', [
      {
        name: 'fake',
        routes: [{ path: '/reports', component: () => <h1>Reports page</h1> }],
        menu: [{ to: '/reports', label: 'Reports', icon: Puzzle }],
      },
    ]);
    expect(await screen.findByRole('heading', { name: 'Reports page' })).toBeTruthy();
    const nav = await screen.findByRole('navigation', { name: strings.nav.primary });
    expect(within(nav).getByRole('link', { name: 'Reports' })).toBeTruthy();
  });

  it('shows the session error with a retry instead of a blank page', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 503, body: { title: 'Service Unavailable', status: 503, request_id: 'req-z' } } });
    renderApp('/');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('req-z');
    expect(screen.getByRole('button', { name: strings.states.retry })).toBeTruthy();
  });
});

describe('first run', () => {
  it('validates the password before sending', () => {
    expect(firstRunValidation('short', 'short')).toBe(strings.firstRun.tooShort);
    expect(firstRunValidation('long-enough-password', 'different-password-1')).toBe(strings.firstRun.mismatch);
    expect(firstRunValidation('long-enough-password', 'long-enough-password')).toBeNull();
  });

  it('shows the form while no account exists and creates the admin', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'GET /api/v1/auth/setup-state': { status: 200, body: { needs_first_run: true } },
      'POST /api/v1/auth/first-run': {
        status: 201,
        body: { user: { ...ADMIN, disabled: false, locked_until: null, created_at: '2026-11-18T00:00:00Z' }, csrf_token: 'c' },
      },
    });
    const { history } = renderApp('/first-run');
    expect(await screen.findByRole('heading', { level: 1, name: strings.firstRun.title })).toBeTruthy();
    await user.type(screen.getByLabelText(strings.firstRun.email), ADMIN.email);
    await user.type(screen.getByLabelText(strings.firstRun.password), 'long-enough-password');
    await user.type(screen.getByLabelText(strings.firstRun.confirm), 'long-enough-password');
    await user.click(screen.getByRole('button', { name: strings.firstRun.submit }));
    await waitFor(() => expect(history.location.pathname).toBe('/'));
  });

  it('shows the 404 state once an account exists', async () => {
    stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'GET /api/v1/auth/setup-state': { status: 200, body: { needs_first_run: false } },
    });
    renderApp('/first-run');
    expect(await screen.findByRole('heading', { level: 1, name: strings.notFound.title })).toBeTruthy();
    expect(screen.getByText(strings.firstRun.closed)).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.notFound.toLogin })).toBeTruthy();
  });

  it('shows an error with retry when the setup state cannot be read', async () => {
    stubFetch({
      'GET /api/v1/auth/me': UNAUTHENTICATED,
      'GET /api/v1/auth/setup-state': { status: 500, body: { title: 'Internal Server Error', status: 500 } },
    });
    renderApp('/first-run');
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.states.retry })).toBeTruthy();
  });
});

describe('404', () => {
  it('renders the designed not-found page with the path and a way back', async () => {
    stubFetch({ 'GET /api/v1/auth/me': UNAUTHENTICATED });
    renderApp('/no-such-page');
    expect(await screen.findByRole('heading', { level: 1, name: strings.notFound.title })).toBeTruthy();
    expect(screen.getByText('/no-such-page')).toBeTruthy();
    expect(await screen.findByRole('link', { name: strings.notFound.toLogin })).toBeTruthy();
  });

  it('is also what the shell gives for an unknown path when signed in', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: ADMIN } });
    renderApp('/clients/does-not-exist');
    expect(await screen.findByRole('heading', { level: 1, name: strings.notFound.title })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.notFound.toHome })).toBeTruthy();
  });
});
