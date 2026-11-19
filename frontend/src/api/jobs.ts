/** Typed calls of the job routes, CSV export and import (docs/openapi.json). */
import { api, requestBlob } from './client';
import type { components, paths } from './schema';

export type JobOut = components['schemas']['JobOut'];
export type JobPage = components['schemas']['JobPage'];
export type NewJob = components['schemas']['NewJob'];
export type JobPatch = components['schemas']['JobPatch'];
export type PauseRequest = components['schemas']['PauseRequest'];
export type ImportResult = components['schemas']['ImportResult'];
export type ImportProblem = components['schemas']['ImportProblem'];

export type JobKind = JobOut['kind'];
export type JobState = JobOut['state'];
export type ScheduleKind = JobOut['schedule_kind'];
export type WarningPolicy = JobOut['warning_policy'];

export type JobListQuery = NonNullable<paths['/api/v1/jobs']['get']['parameters']['query']>;

export const JOB_KINDS: readonly JobKind[] = ['backup', 'script', 'other'];
export const JOB_STATES: readonly JobState[] = ['ok', 'warning', 'failing', 'missed', 'unknown', 'paused', 'maintenance'];
export const SCHEDULE_KINDS: readonly ScheduleKind[] = ['daily', 'cron', 'interval'];
export const WARNING_POLICIES: readonly WarningPolicy[] = ['warning_is_attention', 'warning_counts_ok'];

const EXPORT_PATH = '/jobs/export.csv';

export const jobsApi = {
  list: (query: JobListQuery = {}, signal?: AbortSignal) =>
    api.get<JobPage>('/jobs', {
      query: {
        client_id: query.client_id ?? undefined,
        q: query.q || undefined,
        state: query.state ?? undefined,
        kind: query.kind ?? undefined,
        pack: query.pack ?? undefined,
        archived: query.archived,
        cursor: query.cursor ?? undefined,
        limit: query.limit,
      },
      signal,
    }),
  get: (jobId: string, signal?: AbortSignal) => api.get<JobOut>(`/jobs/${encodeURIComponent(jobId)}`, { signal }),
  create: (body: NewJob) => api.post<JobOut>('/jobs', { body }),
  update: (jobId: string, body: JobPatch) => api.patch<JobOut>(`/jobs/${encodeURIComponent(jobId)}`, { body }),
  /** Without until the job stays paused until resumed. */
  pause: (jobId: string, body?: PauseRequest) =>
    api.post<JobOut>(`/jobs/${encodeURIComponent(jobId)}/pause`, body ? { body } : {}),
  resume: (jobId: string) => api.post<JobOut>(`/jobs/${encodeURIComponent(jobId)}/resume`),
  archive: (jobId: string) => api.post<JobOut>(`/jobs/${encodeURIComponent(jobId)}/archive`),
  /** The jobs as CSV (all, or one client's). */
  exportCsv: (clientId?: string | null) => requestBlob(EXPORT_PATH, { query: { client_id: clientId ?? undefined } }),
  /** dry_run checks the file and saves nothing; the errors are listed by row. */
  importCsv: (file: File, dryRun: boolean) => {
    const form = new FormData();
    form.append('file', file, file.name || 'jobs.csv');
    return api.post<ImportResult>('/jobs/import.csv', { form, query: { dry_run: dryRun } });
  },
};
