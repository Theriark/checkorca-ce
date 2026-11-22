/**
 * Morning check queries. Every live number polls once a minute while the
 * page is open (dashboard/today, the ribbon, the trend, the breakdown, the
 * activity timeline); an acknowledge refreshes today and the job lists.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { dashboardApi, type ActivityKind, type BreakdownBy, type RibbonQuery, TREND_DAYS } from '../../api/dashboard';
import { jobsApi } from '../../api/jobs';
import { CLIENTS_KEY } from '../clients/queries';
import { JOBS_KEY } from '../jobs/queries';

export const DASHBOARD_KEY = ['dashboard'] as const;
export const ACTIVITY_KEY = ['activity'] as const;
export const DIGEST_KEY = ['digest'] as const;
/** The polling cadence of the morning check (docs/dashboard.md, C8-F). */
export const POLL_INTERVAL_MS = 60_000;
export const ACTIVITY_PAGE_SIZE = 50;

export function useToday(enabled = true) {
  return useQuery({
    queryKey: [...DASHBOARD_KEY, 'today'],
    queryFn: ({ signal }) => dashboardApi.today(signal),
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
}

export function ribbonKey(query: RibbonQuery) {
  return [...DASHBOARD_KEY, 'ribbon', { from: query.from ?? null, to: query.to ?? null, problems_only: query.problems_only ?? false }] as const;
}

export function useRibbon(query: RibbonQuery = {}, enabled = true) {
  return useQuery({
    queryKey: ribbonKey(query),
    queryFn: ({ signal }) => dashboardApi.ribbon(query, signal),
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
    // The problems-only switch keeps the last ribbon on screen while the
    // narrower one loads, instead of a flash of skeleton.
    placeholderData: (previous) => previous,
  });
}

export function useTrend(days: number = TREND_DAYS) {
  return useQuery({
    queryKey: [...DASHBOARD_KEY, 'trend', days],
    queryFn: ({ signal }) => dashboardApi.trend(days, signal),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useBreakdown(by: BreakdownBy, days: number = TREND_DAYS) {
  return useQuery({
    queryKey: [...DASHBOARD_KEY, 'breakdown', by, days],
    queryFn: ({ signal }) => dashboardApi.breakdown(by, days, signal),
    refetchInterval: POLL_INTERVAL_MS,
    placeholderData: (previous) => previous,
  });
}

export function useActivity(kind: ActivityKind | null) {
  return useInfiniteQuery({
    queryKey: [...ACTIVITY_KEY, 'list', kind],
    queryFn: ({ pageParam, signal }) => dashboardApi.activity({ kind, cursor: pageParam, limit: ACTIVITY_PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    // Only the first page is polled: a cursor list refetches every loaded
    // page, so the poll stops once the person asked for more.
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 0) > 1 ? false : POLL_INTERVAL_MS),
  });
}

/** The digest of one day; asked only while the preview is open. */
export function useDigestPreview(date: string | null, enabled: boolean) {
  return useQuery({
    queryKey: [...DIGEST_KEY, 'preview', date],
    queryFn: ({ signal }) => dashboardApi.digestPreview(date, signal),
    enabled,
    staleTime: 60_000,
  });
}

/** Mark a job as looked at. The attention list, the job lists and the
 *  client counts show the new acknowledged_at. */
export function useAcknowledgeJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.acknowledge(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEY });
      void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
      void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
      void queryClient.invalidateQueries({ queryKey: ACTIVITY_KEY });
    },
  });
}
