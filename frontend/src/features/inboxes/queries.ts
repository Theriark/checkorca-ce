/** Inbox queries and mutations on TanStack Query. Every mutation refreshes
 *  the inbox lists, the options other screens use, and the system status
 *  (its inbox activity comes from the same rows). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { inboxesApi, type InboxKind, type InboxOut, type InboxPatch, type NewInbox } from '../../api/inboxes';
import { SYSTEM_KEY } from '../system/queries';

export const INBOXES_KEY = ['inboxes'] as const;
export const PAGE_SIZE = 100;

export interface InboxFilters {
  readonly kind?: InboxKind | null;
}

export function inboxListKey(filters: InboxFilters) {
  return [...INBOXES_KEY, 'list', { kind: filters.kind ?? null }] as const;
}

export function inboxKey(inboxId: string) {
  return [...INBOXES_KEY, 'detail', inboxId] as const;
}

export function useInboxList(filters: InboxFilters) {
  return useInfiniteQuery({
    queryKey: inboxListKey(filters),
    queryFn: ({ pageParam, signal }) => inboxesApi.list({ kind: filters.kind ?? null, cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** Every inbox, for the message filter and the upload dialog. */
export function useInboxOptions(enabled = true) {
  return useQuery({
    queryKey: [...INBOXES_KEY, 'options'],
    enabled,
    queryFn: async ({ signal }) => {
      const items: InboxOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await inboxesApi.list({ cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
  });
}

export function useInbox(inboxId: string) {
  return useQuery({
    queryKey: inboxKey(inboxId),
    queryFn: ({ signal }) => inboxesApi.get(inboxId, signal),
    retry: (count, error) => !(error instanceof Error && 'status' in error && error.status === 404) && count < 1,
  });
}

function useAfterInboxChange() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: INBOXES_KEY });
    void queryClient.invalidateQueries({ queryKey: SYSTEM_KEY });
  };
}

export function useCreateInbox() {
  const after = useAfterInboxChange();
  return useMutation({ mutationFn: (body: NewInbox) => inboxesApi.create(body), onSuccess: after });
}

export function useUpdateInbox() {
  const after = useAfterInboxChange();
  return useMutation({
    mutationFn: ({ inboxId, body }: { readonly inboxId: string; readonly body: InboxPatch }) => inboxesApi.update(inboxId, body),
    onSuccess: after,
  });
}

export function useDeleteInbox() {
  const after = useAfterInboxChange();
  return useMutation({ mutationFn: (inboxId: string) => inboxesApi.remove(inboxId), onSuccess: after });
}

export function useRotateInboxToken() {
  const after = useAfterInboxChange();
  return useMutation({ mutationFn: (inboxId: string) => inboxesApi.rotateToken(inboxId), onSuccess: after });
}
