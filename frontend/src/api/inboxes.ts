/** Typed calls of the inbox routes (docs/openapi.json, docs/ingest.md). */
import { api } from './client';
import type { components, paths } from './schema';

export type InboxOut = components['schemas']['InboxOut'];
export type InboxCreated = components['schemas']['InboxCreated'];
export type InboxPage = components['schemas']['InboxPage'];
export type NewInbox = components['schemas']['NewInbox'];
export type InboxPatch = components['schemas']['InboxPatch'];
export type InboxToken = components['schemas']['InboxToken'];
export type ImapOut = components['schemas']['ImapOut'];
export type ImapSettings = components['schemas']['ImapSettings'];
export type ImapPatch = components['schemas']['ImapPatch'];
export type InboxKind = InboxOut['kind'];

export type InboxListQuery = NonNullable<paths['/api/v1/inboxes']['get']['parameters']['query']>;

export const INBOX_KINDS: readonly InboxKind[] = ['smtp', 'imap', 'webhook', 'upload'];

export const inboxesApi = {
  list: (query: InboxListQuery = {}, signal?: AbortSignal) =>
    api.get<InboxPage>('/inboxes', {
      query: { kind: query.kind ?? undefined, cursor: query.cursor ?? undefined, limit: query.limit },
      signal,
    }),
  get: (inboxId: string, signal?: AbortSignal) => api.get<InboxOut>(`/inboxes/${encodeURIComponent(inboxId)}`, { signal }),
  /** A webhook inbox's token is in this answer only. */
  create: (body: NewInbox) => api.post<InboxCreated>('/inboxes', { body }),
  /** A new IMAP host, port, TLS setting or user name needs the password again (422). */
  update: (inboxId: string, body: InboxPatch) => api.patch<InboxOut>(`/inboxes/${encodeURIComponent(inboxId)}`, { body }),
  remove: (inboxId: string) => api.delete<undefined>(`/inboxes/${encodeURIComponent(inboxId)}`),
  /** A new webhook token, shown once; the old one stops working at once. */
  rotateToken: (inboxId: string) => api.post<InboxToken>(`/inboxes/${encodeURIComponent(inboxId)}/token`),
};
