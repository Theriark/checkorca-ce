/** Typed calls of the message routes and the .eml upload (docs/ingest.md). */
import { api } from './client';
import type { components, paths } from './schema';

export type MessageOut = components['schemas']['MessageOut'];
export type MessageDetail = components['schemas']['MessageDetail'];
export type MessagePage = components['schemas']['MessagePage'];
export type MessageAccepted = components['schemas']['MessageAccepted'];
export type HeaderOut = components['schemas']['HeaderOut'];
export type ResultOut = components['schemas']['ResultOut'];
export type ParseState = MessageOut['parse_state'];
export type ResultStatus = ResultOut['status'];

export type MessageListQuery = NonNullable<paths['/api/v1/messages']['get']['parameters']['query']>;

export const PARSE_STATES: readonly ParseState[] = ['pending', 'parsed', 'unmatched', 'error'];

/** The API's cap on one message: 5 MiB (app.ingest.store.MAX_MESSAGE_BYTES). */
export const MAX_MESSAGE_BYTES = 5 * 1024 * 1024;

export const messagesApi = {
  list: (query: MessageListQuery = {}, signal?: AbortSignal) =>
    api.get<MessagePage>('/messages', {
      query: {
        inbox_id: query.inbox_id ?? undefined,
        parse_state: query.parse_state ?? undefined,
        cursor: query.cursor ?? undefined,
        limit: query.limit,
      },
      signal,
    }),
  get: (messageId: string, signal?: AbortSignal) => api.get<MessageDetail>(`/messages/${encodeURIComponent(messageId)}`, { signal }),
  /** multipart: the .eml as `file` and the inbox as `inbox_id`; the client
   *  sends the CSRF token with every POST. 413 above 5 MiB, 422 for a file
   *  that is no e-mail message, 404 for an unknown inbox. */
  upload: (file: File, inboxId: string) => {
    const form = new FormData();
    form.append('file', file, file.name || 'message.eml');
    form.append('inbox_id', inboxId);
    return api.post<MessageAccepted>('/messages/upload', { form });
  },
};
