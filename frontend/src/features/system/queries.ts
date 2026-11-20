/** The system status (worker heartbeat, inbox activity, queue). The shell
 *  asks for it once a minute while signed in, so the stale-heartbeat banner
 *  appears within a minute of the worker stopping. */
import { useQuery } from '@tanstack/react-query';

import { systemApi } from '../../api/system';

export const SYSTEM_KEY = ['system'] as const;
export const STATUS_KEY = [...SYSTEM_KEY, 'status'] as const;
export const STATUS_INTERVAL_MS = 60_000;

export function useSystemStatus(enabled = true) {
  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: ({ signal }) => systemApi.status(signal),
    enabled,
    staleTime: 30_000,
    refetchInterval: STATUS_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}
