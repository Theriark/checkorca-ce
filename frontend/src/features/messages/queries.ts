/** Message queries and the .eml upload. An upload refreshes the message
 *  lists, the inboxes (last_message_at) and the system status (the queue). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { messagesApi, type MessageListQuery } from '../../api/messages';
import { INBOXES_KEY } from '../inboxes/queries';
import { SYSTEM_KEY } from '../system/queries';

export const MESSAGES_KEY = ['messages'] as const;
export const PAGE_SIZE = 100;

export type MessageFilters = Pick<MessageListQuery, 'inbox_id' | 'parse_state'>;

export function messageListKey(filters: MessageFilters) {
  return [...MESSAGES_KEY, 'list', { inbox_id: filters.inbox_id ?? null, parse_state: filters.parse_state ?? null }] as const;
}

export function messageKey(messageId: string) {
  return [...MESSAGES_KEY, 'detail', messageId] as const;
}

export function useMessageList(filters: MessageFilters) {
  return useInfiniteQuery({
    queryKey: messageListKey(filters),
    queryFn: ({ pageParam, signal }) => messagesApi.list({ ...filters, cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function useMessage(messageId: string) {
  return useQuery({
    queryKey: messageKey(messageId),
    queryFn: ({ signal }) => messagesApi.get(messageId, signal),
    retry: (count, error) => !(error instanceof Error && 'status' in error && error.status === 404) && count < 1,
  });
}

export function useUploadMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, inboxId }: { readonly file: File; readonly inboxId: string }) => messagesApi.upload(file, inboxId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MESSAGES_KEY });
      void queryClient.invalidateQueries({ queryKey: INBOXES_KEY });
      void queryClient.invalidateQueries({ queryKey: SYSTEM_KEY });
    },
  });
}

/** The ids of the loaded messages whose Message-ID another loaded message
 *  shares: the same mail stored in two inboxes (the API keeps one row per
 *  inbox). Messages without a Message-ID are never flagged. */
export function duplicateIds(messages: readonly { readonly id: string; readonly message_id: string | null }[]): ReadonlySet<string> {
  const byMessageId = new Map<string, string[]>();
  for (const message of messages) {
    if (message.message_id) {
      const ids = byMessageId.get(message.message_id) ?? [];
      ids.push(message.id);
      byMessageId.set(message.message_id, ids);
    }
  }
  const flagged = new Set<string>();
  for (const ids of byMessageId.values()) {
    if (ids.length > 1) {
      for (const id of ids) {
        flagged.add(id);
      }
    }
  }
  return flagged;
}

/** "12.3 KB" or "4.8 MB" for a message size. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
