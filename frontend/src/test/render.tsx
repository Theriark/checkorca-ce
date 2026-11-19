/* Test helpers: providers, a memory-history app, and a fetch stub that
   answers the auth routes. */
import { RouterProvider, createMemoryHistory } from '@tanstack/react-router';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement } from 'react';
import { vi } from 'vitest';

import type { FrontendPlugin } from '../plugins/index';
import { createAppRouter } from '../router';
import { Providers } from './Providers';


export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: Providers, ...options });
}

/** The whole app at a path, with a memory history. */
export function renderApp(path: string, plugins?: readonly FrontendPlugin[]) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const view = render(
    <Providers plugins={plugins}>
      <RouterProvider router={router} />
    </Providers>,
  );
  return { ...view, router, history };
}

export type FetchAnswer =
  | { readonly status: number; readonly body?: unknown; readonly headers?: Record<string, string> }
  | ((input: string, init: RequestInit | undefined) => { readonly status: number; readonly body?: unknown; readonly headers?: Record<string, string> });

/** Stub fetch by "METHOD /api/v1/path" (query string ignored). */
export function stubFetch(routes: Record<string, FetchAnswer>) {
  const calls: { readonly method: string; readonly url: string; readonly init: RequestInit | undefined }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ method, url, init });
    const key = `${method} ${url.split('?')[0]}`;
    const answer = routes[key];
    if (!answer) {
      return new Response(JSON.stringify({ title: 'Not Found', status: 404, detail: `No stub for ${key}` }), {
        status: 404,
        headers: { 'content-type': 'application/problem+json' },
      });
    }
    const resolved = typeof answer === 'function' ? answer(url, init) : answer;
    const headers = {
      'content-type': resolved.status >= 400 ? 'application/problem+json' : 'application/json',
      ...resolved.headers,
    };
    return new Response(resolved.status === 204 ? null : JSON.stringify(resolved.body ?? {}), {
      status: resolved.status,
      headers,
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

export const ADMIN = {
  id: '11111111-1111-4111-8111-111111111111',
  email: 'checkorca.admin@example.com',
  role: 'admin' as const,
  csrf_token: 'csrf-admin',
};

export const TECHNICIAN = {
  id: '22222222-2222-4222-8222-222222222222',
  email: 'checkorca.technician@example.com',
  role: 'technician' as const,
  csrf_token: 'csrf-tech',
};

export const UNAUTHENTICATED = { status: 401, body: { title: 'Unauthorized', status: 401 } };
