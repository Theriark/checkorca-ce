/** Typed calls of the system routes (docs/ingest.md, Readiness and System status). */
import { api } from './client';
import type { components } from './schema';

export type SystemStatus = components['schemas']['SystemStatus'];
export type WorkerStatus = components['schemas']['WorkerStatus'];

export const systemApi = {
  status: (signal?: AbortSignal) => api.get<SystemStatus>('/system/status', { signal }),
};
