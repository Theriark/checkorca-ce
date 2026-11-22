/** Job queries and mutations. Job changes also refresh the clients (their
 *  counts and worst state come from the jobs). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import { flipsApi, jobsApi, type FlipQuery, type JobListQuery, type JobOut, type JobPatch, type NewJob, type OccurrenceOut, type PauseRequest } from '../../api/jobs';
import { CLIENTS_KEY } from '../clients/queries';

export const JOBS_KEY = ['jobs'] as const;
export const PAGE_SIZE = 100;

export type JobFilters = Pick<JobListQuery, 'client_id' | 'q' | 'state' | 'kind' | 'archived'>;

export function jobListKey(filters: JobFilters) {
  return [
    ...JOBS_KEY,
    'list',
    {
      client_id: filters.client_id ?? null,
      q: filters.q ?? '',
      state: filters.state ?? null,
      kind: filters.kind ?? null,
      archived: filters.archived ?? false,
    },
  ] as const;
}

export function useJobList(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: jobListKey(filters),
    queryFn: ({ pageParam, signal }) => jobsApi.list({ ...filters, cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function jobKey(jobId: string) {
  return [...JOBS_KEY, 'detail', jobId] as const;
}

/** One job; a 404 is an answer (the not-found state), not retried. */
export function useJob(jobId: string) {
  return useQuery({
    queryKey: jobKey(jobId),
    queryFn: ({ signal }) => jobsApi.get(jobId, signal),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
    refetchInterval: 60_000,
  });
}

/** The runs of a job in a window (the 30-day strip and the history). */
export function useOccurrences(jobId: string, from: string, to: string, enabled = true) {
  return useQuery({
    queryKey: [...JOBS_KEY, 'occurrences', jobId, from, to],
    queryFn: async ({ signal }) => {
      const items: OccurrenceOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await jobsApi.occurrences(jobId, { from, to, cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
    enabled,
    refetchInterval: 60_000,
    // At midnight the window moves; keep the old strip until the new one is in.
    placeholderData: (previous) => previous,
  });
}

/** The newest results of a job (first page). */
export function useJobResults(jobId: string, enabled = true) {
  return useQuery({
    queryKey: [...JOBS_KEY, 'results', jobId],
    queryFn: ({ signal }) => jobsApi.results(jobId, { limit: 50 }, signal),
    enabled,
    refetchInterval: 60_000,
  });
}

/** The state changes of a job or a client, newest first. */
export function useFlips(query: Pick<FlipQuery, 'job_id' | 'client_id'>, enabled = true) {
  return useInfiniteQuery({
    queryKey: [...JOBS_KEY, 'flips', { job_id: query.job_id ?? null, client_id: query.client_id ?? null }],
    queryFn: ({ pageParam, signal }) => flipsApi.list({ ...query, cursor: pageParam, limit: 50 }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled,
  });
}

function useAfterJobChange() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
    void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
  };
}

export function useCreateJob() {
  const after = useAfterJobChange();
  return useMutation({ mutationFn: (body: NewJob) => jobsApi.create(body), onSuccess: after });
}

export function useUpdateJob() {
  const after = useAfterJobChange();
  return useMutation({
    mutationFn: ({ jobId, body }: { readonly jobId: string; readonly body: JobPatch }) => jobsApi.update(jobId, body),
    onSuccess: after,
  });
}

export function usePauseJob() {
  const after = useAfterJobChange();
  return useMutation({
    mutationFn: ({ jobId, body }: { readonly jobId: string; readonly body?: PauseRequest }) => jobsApi.pause(jobId, body),
    onSuccess: after,
  });
}

export function useResumeJob() {
  const after = useAfterJobChange();
  return useMutation({ mutationFn: (jobId: string) => jobsApi.resume(jobId), onSuccess: after });
}

export function useArchiveJob() {
  const after = useAfterJobChange();
  return useMutation({ mutationFn: (jobId: string) => jobsApi.archive(jobId), onSuccess: after });
}

export function useRestoreJob() {
  const after = useAfterJobChange();
  return useMutation({ mutationFn: (jobId: string) => jobsApi.update(jobId, { archived: false }), onSuccess: after });
}

export function useImportJobs() {
  const after = useAfterJobChange();
  return useMutation({
    mutationFn: ({ file, dryRun }: { readonly file: File; readonly dryRun: boolean }) => jobsApi.importCsv(file, dryRun),
    onSuccess: (result) => {
      if (!result.dry_run) {
        after();
      }
    },
  });
}

/** True while the job is paused (enabled false, or paused_until ahead). */
export function isPaused(job: JobOut, now: Date = new Date()): boolean {
  return !job.enabled || (job.paused_until !== null && new Date(job.paused_until) > now);
}
