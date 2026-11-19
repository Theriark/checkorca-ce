/** Job queries and mutations. Job changes also refresh the clients (their
 *  counts and worst state come from the jobs). */
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { jobsApi, type JobListQuery, type JobOut, type JobPatch, type NewJob, type PauseRequest } from '../../api/jobs';
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
