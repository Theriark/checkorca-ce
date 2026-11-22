/**
 * The note a polled page shows when a refresh failed while data was already
 * on screen: the last answer stays (TanStack Query keeps data on a refetch
 * error) and the note names the time it was received. With several queries,
 * the oldest data among those that failed sets the time, so the note never
 * claims a fresher time than what is drawn. Nothing while every query is
 * fresh or still loading for the first time (that is the error state).
 */
import { fill, formatTime } from '../../lib/format';
import { strings } from '../../strings';
import '../dashboard/dashboard.css';

export interface StaleQuery {
  readonly isRefetchError: boolean;
  readonly dataUpdatedAt: number;
}

/** The receipt time (ms) of the oldest data whose refresh failed, or null. */
export function staleSince(queries: readonly StaleQuery[]): number | null {
  const times = queries.filter((query) => query.isRefetchError && query.dataUpdatedAt > 0).map((query) => query.dataUpdatedAt);
  return times.length === 0 ? null : Math.min(...times);
}

export function StaleNote({ queries }: { readonly queries: readonly StaleQuery[] }) {
  const since = staleSince(queries);
  if (since === null) {
    return null;
  }
  return (
    <span className="co-dash__refreshing" data-testid="stale-data">
      {fill(strings.dashboard.staleData, { time: formatTime(new Date(since).toISOString()) })}
    </span>
  );
}
