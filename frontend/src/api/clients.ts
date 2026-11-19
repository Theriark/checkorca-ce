/** Typed calls of the client routes (docs/openapi.json, phase C3-B). */
import { api } from './client';
import type { components } from './schema';

export type ClientOut = components['schemas']['ClientOut'];
export type ClientPage = components['schemas']['ClientPage'];
export type NewClient = components['schemas']['NewClient'];
export type ClientPatch = components['schemas']['ClientPatch'];

export interface ClientListQuery {
  readonly q?: string;
  readonly archived?: boolean;
  readonly cursor?: string | null;
  readonly limit?: number;
}

export const clientsApi = {
  list: (query: ClientListQuery = {}, signal?: AbortSignal) =>
    api.get<ClientPage>('/clients', {
      query: { q: query.q || undefined, archived: query.archived, cursor: query.cursor ?? undefined, limit: query.limit },
      signal,
    }),
  get: (clientId: string, signal?: AbortSignal) => api.get<ClientOut>(`/clients/${encodeURIComponent(clientId)}`, { signal }),
  create: (body: NewClient) => api.post<ClientOut>('/clients', { body }),
  update: (clientId: string, body: ClientPatch) => api.patch<ClientOut>(`/clients/${encodeURIComponent(clientId)}`, { body }),
  archive: (clientId: string) => api.post<ClientOut>(`/clients/${encodeURIComponent(clientId)}/archive`),
  /** confirm_name must equal the client's name; 409 otherwise. */
  remove: (clientId: string, confirmName: string) =>
    api.delete<undefined>(`/clients/${encodeURIComponent(clientId)}`, { query: { confirm_name: confirmName } }),
};
