/** Unmatched queries and mutations. An assign or create-job changes jobs,
 *  clients (aliases), messages (client links) and the queue itself, so every
 *  one of those is refreshed. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import { jobsApi } from '../../api/jobs';
import { messagesApi } from '../../api/messages';
import { unmatchedApi, type AssignRequest, type CreateJobRequest } from '../../api/unmatched';
import { CLIENTS_KEY } from '../clients/queries';
import { JOBS_KEY } from '../jobs/queries';
import { MESSAGES_KEY, messageKey } from '../messages/queries';

export const UNMATCHED_KEY = ['unmatched'] as const;
export const PAGE_SIZE = 100;
/** Jobs shown in the assign dialog for one search. */
export const JOB_SEARCH_LIMIT = 50;

export function useUnmatchedList() {
  return useInfiniteQuery({
    queryKey: [...UNMATCHED_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => unmatchedApi.list({ cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** The raw message of a result; nothing is asked without an id, and a purged
 *  message (404) is not retried. */
export function useRawMessage(messageId: string | null) {
  return useQuery({
    queryKey: messageKey(messageId ?? 'none'),
    queryFn: ({ signal }) => messagesApi.get(messageId ?? '', signal),
    enabled: messageId !== null,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
}

/** The jobs that match a search, for the assign dialog. */
export function useJobSearch(q: string, enabled: boolean) {
  return useQuery({
    queryKey: [...JOBS_KEY, 'search', q],
    queryFn: ({ signal }) => jobsApi.list({ q: q || undefined, archived: false, limit: JOB_SEARCH_LIMIT }, signal),
    enabled,
    staleTime: 10_000,
  });
}

function useAfterBinding() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: UNMATCHED_KEY });
    void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
    void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
    void queryClient.invalidateQueries({ queryKey: MESSAGES_KEY });
  };
}

export function useAssignResult() {
  const after = useAfterBinding();
  return useMutation({
    mutationFn: ({ resultId, body }: { readonly resultId: string; readonly body: AssignRequest }) => unmatchedApi.assign(resultId, body),
    onSuccess: after,
  });
}

export function useCreateJobFromResult() {
  const after = useAfterBinding();
  return useMutation({
    mutationFn: ({ resultId, body }: { readonly resultId: string; readonly body: CreateJobRequest }) => unmatchedApi.createJob(resultId, body),
    onSuccess: after,
  });
}

/** PATCH the job's match key (the jobs route). Used after an assign that kept
 *  another key: the result is bound by then, so a second assign of the same
 *  result would answer 409 (app/api/v1/unmatched.py, unmatched_result). */
export function useReplaceMatchKey() {
  const after = useAfterBinding();
  return useMutation({
    mutationFn: ({ jobId, matchKey }: { readonly jobId: string; readonly matchKey: string }) => jobsApi.update(jobId, { match_key: matchKey }),
    onSuccess: after,
  });
}

/** The schedule suggestion for a result in a zone; asked only when wanted. A
 *  422 (too few runs, unknown zone) is an answer, not retried. */
export function useScheduleSuggestion(resultId: string | null, timezone: string, enabled: boolean) {
  return useQuery({
    queryKey: [...UNMATCHED_KEY, 'suggest', resultId, timezone],
    queryFn: ({ signal }) => unmatchedApi.suggestSchedule(resultId ?? '', timezone, signal),
    enabled: enabled && resultId !== null,
    retry: false,
    staleTime: 60_000,
  });
}
