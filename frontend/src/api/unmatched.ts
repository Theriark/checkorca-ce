/** Typed calls of the Unmatched routes: the queue of results no job claimed
 *  and the three ways out of it (docs/parsers.md, Packs and Unmatched API). */
import { api } from './client';
import type { components, paths } from './schema';

export type UnmatchedOut = components['schemas']['UnmatchedOut'];
export type UnmatchedPage = components['schemas']['UnmatchedPage'];
export type AssignRequest = components['schemas']['AssignRequest'];
export type Binding = components['schemas']['Binding'];
export type AliasReason = NonNullable<Binding['reason']>;
export type CreateJobRequest = components['schemas']['CreateJobRequest'];
export type JobFromResult = components['schemas']['JobFromResult'];
export type ScheduleSuggestion = components['schemas']['ScheduleSuggestion'];
export type SuggestionBasis = ScheduleSuggestion['basis'];

export type UnmatchedListQuery = NonNullable<paths['/api/v1/unmatched']['get']['parameters']['query']>;

export const unmatchedApi = {
  list: (query: UnmatchedListQuery = {}, signal?: AbortSignal) =>
    api.get<UnmatchedPage>('/unmatched', { query: { cursor: query.cursor ?? undefined, limit: query.limit }, signal }),
  /** Bind the result to an existing job. The job takes the result's job name
   *  as its match key when it had none or, with replace_match_key, when its
   *  key names another job name. 422 for an unknown job, 409 when the result
   *  is bound already. */
  assign: (resultId: string, body: AssignRequest) => api.post<Binding>(`/unmatched/${encodeURIComponent(resultId)}/assign`, { body }),
  /** A new job (and, by name, a new client) from the result, bound the same
   *  way. 409 when the client has a job of that name. */
  createJob: (resultId: string, body: CreateJobRequest) => api.post<JobFromResult>(`/unmatched/${encodeURIComponent(resultId)}/create-job`, { body }),
  /** A daily schedule at the median time of the runs with the same names;
   *  422 below three runs or for an unknown zone. */
  suggestSchedule: (resultId: string, timezone: string | null, signal?: AbortSignal) =>
    api.get<ScheduleSuggestion>(`/unmatched/${encodeURIComponent(resultId)}/suggest-schedule`, { query: { timezone: timezone ?? undefined }, signal }),
};
