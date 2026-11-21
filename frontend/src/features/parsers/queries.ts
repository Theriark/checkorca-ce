/** Parser pack queries and mutations. A saved, imported, enabled or disabled
 *  pack refreshes the list and its detail. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import { packsApi, type PackTestRequest } from '../../api/packs';

export const PACKS_KEY = ['packs'] as const;
export const PAGE_SIZE = 100;

export function packKey(packId: string) {
  return [...PACKS_KEY, 'detail', packId] as const;
}

export function usePackList() {
  return useInfiniteQuery({
    queryKey: [...PACKS_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => packsApi.list({ cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function usePack(packId: string) {
  return useQuery({
    queryKey: packKey(packId),
    queryFn: ({ signal }) => packsApi.get(packId, signal),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
}

function useAfterPackChange() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: PACKS_KEY });
}

export function useSavePack() {
  const after = useAfterPackChange();
  return useMutation({
    mutationFn: ({ packId, yaml }: { readonly packId: string; readonly yaml: string }) => packsApi.put(packId, yaml),
    onSuccess: after,
  });
}

export function useImportPack() {
  const after = useAfterPackChange();
  return useMutation({ mutationFn: (file: File) => packsApi.importFile(file), onSuccess: after });
}

export function useSetPackEnabled() {
  const after = useAfterPackChange();
  return useMutation({
    mutationFn: ({ packId, enabled }: { readonly packId: string; readonly enabled: boolean }) => (enabled ? packsApi.enable(packId) : packsApi.disable(packId)),
    onSuccess: after,
  });
}

/** One bench run; nothing is cached (the answer belongs to one click). */
export function useBenchRun() {
  return useMutation({ mutationFn: (body: PackTestRequest) => packsApi.test(body) });
}
