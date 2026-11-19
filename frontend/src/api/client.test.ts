import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, CSRF_HEADER, api, request, setCsrfToken, toApiError } from './client';

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

describe('api client', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    setCsrfToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends same-origin JSON requests under /api/v1', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { needs_first_run: false }));
    const result = await api.get<{ needs_first_run: boolean }>('/auth/setup-state');
    expect(result).toEqual({ needs_first_run: false });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/setup-state');
    expect(init.credentials).toBe('same-origin');
    expect(init.method).toBe('GET');
    expect((init.headers as Headers).has(CSRF_HEADER)).toBe(false);
  });

  it('adds X-CSRF-Token to state-changing requests once a session token is known', async () => {
    fetchMock.mockResolvedValue(jsonResponse(204, null));
    setCsrfToken('csrf-123');
    await api.post('/auth/logout');
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Headers).get(CSRF_HEADER)).toBe('csrf-123');
    expect((init.headers as Headers).get('Content-Type')).toBeNull();
  });

  it('serialises a body and a query string', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [], next_cursor: null }));
    await request('GET', '/users', { query: { limit: 50, cursor: undefined, archived: false } });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/users?limit=50&archived=false');
    fetchMock.mockResolvedValue(jsonResponse(201, { ok: true }));
    await api.post('/users', { body: { email: 'a@example.com' } });
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.body).toBe('{"email":"a@example.com"}');
    expect((init.headers as Headers).get('Content-Type')).toBe('application/json');
  });

  it('maps a problem details answer to ApiError with request id and field errors', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          type: 'about:blank',
          title: 'Unprocessable Entity',
          status: 422,
          detail: 'Invalid input',
          request_id: 'req-9',
          errors: [{ field: 'body.email', message: 'Not an e-mail address' }],
        }),
        { status: 422, headers: { 'content-type': 'application/problem+json' } },
      ),
    );
    const error = await api.post('/users', { body: {} }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.requestId).toBe('req-9');
    expect(apiError.fieldMessage('email')).toBe('Not an e-mail address');
    expect(apiError.message).toBe('Unprocessable Entity: Invalid input');
  });

  it('reads Retry-After and the request id header of a lockout', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        423,
        { title: 'Locked', status: 423 },
        { 'retry-after': '300', 'x-request-id': 'req-lock' },
      ),
    );
    const error = (await api.post('/auth/login', { body: {} }).catch((caught: unknown) => caught)) as ApiError;
    expect(error.status).toBe(423);
    expect(error.retryAfterSeconds).toBe(300);
    expect(error.requestId).toBe('req-lock');
  });

  it('maps a non-JSON failure to an ApiError with the HTTP status', async () => {
    fetchMock.mockResolvedValue(new Response('<html>', { status: 502, statusText: 'Bad Gateway' }));
    const error = (await api.get('/auth/me').catch((caught: unknown) => caught)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.title).toBe('Bad Gateway');
    expect(error.isNetworkError).toBe(false);
  });

  it('maps a network failure to status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const error = (await api.get('/auth/me').catch((caught: unknown) => caught)) as ApiError;
    expect(error.isNetworkError).toBe(true);
    expect(error.status).toBe(0);
  });

  it('wraps unknown errors', () => {
    const wrapped = toApiError(new Error('boom'));
    expect(wrapped.isNetworkError).toBe(true);
    expect(wrapped.detail).toBe('boom');
    const same = new ApiError({ title: 'x', status: 400 });
    expect(toApiError(same)).toBe(same);
  });
});
