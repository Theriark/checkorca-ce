/**
 * The one HTTP client of the web app.
 *
 * - Same-origin requests with the session cookie.
 * - Every state-changing request carries X-CSRF-Token (docs/auth.md).
 * - Errors are RFC 9457 problem details, mapped to ApiError with the status,
 *   the title and detail, the field errors and the request id for support.
 * - A network failure or a non-JSON answer becomes an ApiError too, so every
 *   caller handles one error type.
 */
import type { components } from './schema';

export type Problem = components['schemas']['Problem'];
export type FieldProblem = components['schemas']['FieldProblem'];
export type PackProblem = components['schemas']['PackProblem'];

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export const API_BASE = '/api/v1';
export const CSRF_HEADER = 'X-CSRF-Token';
export const REQUEST_ID_HEADER = 'X-Request-ID';

/** Status 0: the request never got an HTTP answer. */
export const NETWORK_ERROR_STATUS = 0;

export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | null;
  readonly type: string;
  readonly requestId: string | null;
  readonly errors: readonly FieldProblem[];
  /** The issues of a parser pack that does not load (422 of the pack routes):
   *  a JSON Pointer into the pack and a message each. */
  readonly issues: readonly PackProblem[];
  readonly retryAfterSeconds: number | null;

  constructor(problem: Problem, options: { requestId?: string | null; retryAfterSeconds?: number | null } = {}) {
    super(problem.detail ? `${problem.title}: ${problem.detail}` : problem.title);
    this.name = 'ApiError';
    this.status = problem.status;
    this.title = problem.title;
    this.detail = problem.detail ?? null;
    this.type = problem.type ?? 'about:blank';
    this.requestId = options.requestId ?? problem.request_id ?? null;
    this.errors = problem.errors ?? [];
    this.issues = problem.issues ?? [];
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }

  /** True when the request never reached the server or got no HTTP answer. */
  get isNetworkError(): boolean {
    return this.status === NETWORK_ERROR_STATUS;
  }

  /** The message for one field, when the server reported it. */
  fieldMessage(field: string): string | undefined {
    const suffix = `.${field}`;
    return this.errors.find((item) => item.field === field || item.field.endsWith(suffix))?.message;
  }
}

/** The CSRF token of the current session, kept in memory only. */
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

export interface RequestOptions {
  readonly body?: unknown;
  /** A multipart body (file upload); the browser sets the content type. */
  readonly form?: FormData;
  readonly query?: Record<string, string | number | boolean | null | undefined>;
  readonly signal?: AbortSignal;
}

export function buildUrl(path: string, query: RequestOptions['query']): string {
  const url = path.startsWith('/') ? `${API_BASE}${path}` : `${API_BASE}/${path}`;
  if (!query) {
    return url;
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `${url}?${encoded}` : url;
}

function isProblem(value: unknown): value is Problem {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { title?: unknown }).title === 'string' &&
    typeof (value as { status?: unknown }).status === 'number'
  );
}

function networkProblem(detail: string): Problem {
  return { type: 'about:blank', title: 'No answer from the server', status: NETWORK_ERROR_STATUS, detail };
}

function parseRetryAfter(header: string | null): number | null {
  if (!header) {
    return null;
  }
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

/** Map an HTTP answer that is not ok to an ApiError. */
export async function problemFromResponse(response: Response): Promise<ApiError> {
  const requestId = response.headers.get(REQUEST_ID_HEADER);
  const retryAfterSeconds = parseRetryAfter(response.headers.get('Retry-After'));
  const payload: unknown = await response.json().catch(() => null);
  const problem: Problem = isProblem(payload)
    ? payload
    : { type: 'about:blank', title: response.statusText || `HTTP ${response.status}`, status: response.status };
  return new ApiError(problem, { requestId, retryAfterSeconds });
}

/**
 * Send one request and return the parsed JSON body (undefined for 204).
 * Throws ApiError for every failure.
 */
export async function request<T>(method: HttpMethod, path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers({ Accept: 'application/json, application/problem+json' });
  const init: RequestInit = { method, headers, credentials: 'same-origin', signal: options.signal ?? null };
  if (options.form !== undefined) {
    init.body = options.form;
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(options.body);
  }
  if (method !== 'GET' && csrfToken) {
    headers.set(CSRF_HEADER, csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError(networkProblem('The request did not reach the server.'));
  }

  if (!response.ok) {
    throw await problemFromResponse(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(networkProblem('The server answered with something that is not JSON.'));
  }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options),
  post: <T>(path: string, options?: RequestOptions) => request<T>('POST', path, options),
  patch: <T>(path: string, options?: RequestOptions) => request<T>('PATCH', path, options),
  put: <T>(path: string, options?: RequestOptions) => request<T>('PUT', path, options),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
};

/**
 * Fetch a file (a CSV export, a pack's YAML) as a Blob with the session
 * cookie. Errors are problem details like everywhere else; the caller saves
 * the Blob. `accept` names the media type expected (text/csv by default).
 */
export async function requestBlob(path: string, options: Pick<RequestOptions, 'query' | 'signal'> & { readonly accept?: string } = {}): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: 'GET',
      credentials: 'same-origin',
      signal: options.signal ?? null,
      headers: { Accept: `${options.accept ?? 'text/csv'}, application/problem+json` },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError(networkProblem('The request did not reach the server.'));
  }
  if (!response.ok) {
    throw await problemFromResponse(response);
  }
  return response.blob();
}

/** Narrow an unknown thrown value to ApiError, wrapping anything else. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  const detail = error instanceof Error ? error.message : 'Unknown error';
  return new ApiError(networkProblem(detail));
}
