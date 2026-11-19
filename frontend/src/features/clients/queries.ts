/** Client queries and mutations on TanStack Query. Every mutation invalidates
 *  the client lists and details; job mutations do too (counts change). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { clientsApi, type ClientListQuery, type ClientOut, type ClientPatch, type NewClient } from '../../api/clients';

export const CLIENTS_KEY = ['clients'] as const;
export const PAGE_SIZE = 100;

export function clientListKey(query: Pick<ClientListQuery, 'q' | 'archived'>) {
  return [...CLIENTS_KEY, 'list', { q: query.q ?? '', archived: query.archived ?? false }] as const;
}

export function clientKey(clientId: string) {
  return [...CLIENTS_KEY, 'detail', clientId] as const;
}

export function useClientList(query: Pick<ClientListQuery, 'q' | 'archived'>) {
  return useInfiniteQuery({
    queryKey: clientListKey(query),
    queryFn: ({ pageParam, signal }) => clientsApi.list({ ...query, cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** The clients a job can belong to (not archived), for selects. */
export function useClientOptions() {
  return useQuery({
    queryKey: [...CLIENTS_KEY, 'options'],
    queryFn: async ({ signal }) => {
      const items: ClientOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await clientsApi.list({ archived: false, cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
  });
}

export function useClient(clientId: string) {
  return useQuery({
    queryKey: clientKey(clientId),
    queryFn: ({ signal }) => clientsApi.get(clientId, signal),
    retry: (count, error) => !(error instanceof Error && 'status' in error && error.status === 404) && count < 1,
  });
}

export function useInvalidateClients() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
}

export function useCreateClient() {
  const invalidate = useInvalidateClients();
  return useMutation({
    mutationFn: (body: NewClient) => clientsApi.create(body),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateClient(clientId: string) {
  const invalidate = useInvalidateClients();
  return useMutation({
    mutationFn: (body: ClientPatch) => clientsApi.update(clientId, body),
    onSuccess: () => void invalidate(),
  });
}

export function useArchiveClient(clientId: string) {
  const invalidate = useInvalidateClients();
  return useMutation({
    mutationFn: () => clientsApi.archive(clientId),
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteClient(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (confirmName: string) => clientsApi.remove(clientId, confirmName),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: clientKey(clientId) });
      void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}
