/**
 * The live preview of a schedule: the next five times from
 * POST schedule/preview, asked 400 ms after the last keystroke. An unusable
 * schedule is an answer (error and field), a failed request is reported
 * separately, and the last good answer stays on screen while a new one loads.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { toApiError } from '../../api/client';
import { scheduleApi, type SchedulePreview } from '../../api/schedule';
import type { ScheduleKind } from '../../api/jobs';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { strings } from '../../strings';

export const PREVIEW_DEBOUNCE_MS = 400;
export const PREVIEW_COUNT = 5;

export interface ScheduleInput {
  readonly kind: ScheduleKind;
  readonly expr: string;
  readonly timezone: string;
  /** The job's creation time for an existing job (interval anchor). */
  readonly anchor?: string | null;
}

export type PreviewState =
  | { readonly status: 'idle' }
  | { readonly status: 'checking'; readonly previous: SchedulePreview | null }
  | { readonly status: 'ready'; readonly preview: SchedulePreview }
  | { readonly status: 'invalid'; readonly message: string; readonly field: string | null }
  | { readonly status: 'failed'; readonly message: string };

export function useSchedulePreview(input: ScheduleInput): PreviewState {
  const { kind, expr, timezone, anchor } = input;
  const trimmedExpr = expr.trim();
  const trimmedZone = timezone.trim();
  const current = useMemo(
    () => ({ kind, expr: trimmedExpr, timezone: trimmedZone, anchor: anchor ?? null }),
    [kind, trimmedExpr, trimmedZone, anchor],
  );
  const settled = useDebouncedValue(current, PREVIEW_DEBOUNCE_MS);
  const complete = settled.expr.length > 0 && settled.timezone.length > 0;

  const query = useQuery({
    queryKey: ['schedule', 'preview', settled],
    queryFn: ({ signal }) =>
      scheduleApi.preview(
        { kind: settled.kind, expr: settled.expr, timezone: settled.timezone, count: PREVIEW_COUNT, anchor: settled.anchor },
        signal,
      ),
    enabled: complete,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });

  if (current.expr.length === 0 || current.timezone.length === 0) {
    return { status: 'idle' };
  }
  const pending = settled !== current || query.isFetching;
  if (pending) {
    const previous = query.data && !query.data.error ? query.data : null;
    return { status: 'checking', previous };
  }
  if (query.isError) {
    const error = toApiError(query.error);
    const fieldMessage = error.errors[0]?.message;
    return { status: 'failed', message: fieldMessage ?? error.detail ?? strings.schedule.unavailable };
  }
  if (!query.data) {
    return { status: 'checking', previous: null };
  }
  if (query.data.error) {
    return { status: 'invalid', message: query.data.error, field: query.data.field };
  }
  return { status: 'ready', preview: query.data };
}
