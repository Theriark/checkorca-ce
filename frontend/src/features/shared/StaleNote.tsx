/**
 * The note a polled page shows when a refresh failed while data was already
 * on screen: the last answer stays (TanStack Query keeps data on a refetch
 * error) and the note names the time it was received, the oldest among the
 * queries that failed. Nothing while every query is fresh or still loading
 * for the first time (that is the error state).
 */
import { fill, formatTime } from '../../lib/format';
import { strings } from '../../strings';
import { staleSince, type StaleQuery } from './staleSince';
import '../dashboard/dashboard.css';

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
