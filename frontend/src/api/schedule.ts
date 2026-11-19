/** The schedule preview: the next times, or why the schedule cannot be used. */
import { api } from './client';
import type { components } from './schema';

export type SchedulePreview = components['schemas']['SchedulePreview'];
export type SchedulePreviewRequest = components['schemas']['SchedulePreviewRequest'];

export const scheduleApi = {
  preview: (body: SchedulePreviewRequest, signal?: AbortSignal) =>
    api.post<SchedulePreview>('/schedule/preview', { body, signal }),
};
