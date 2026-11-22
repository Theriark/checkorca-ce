/** The shape of a polled query the stale note reads (a TanStack Query result). */
export interface StaleQuery {
  readonly isRefetchError: boolean;
  readonly dataUpdatedAt: number;
}

/**
 * The receipt time (ms) of the oldest data whose refresh failed, or null
 * while every query is fresh or still loading for the first time. The
 * oldest sets the time so the note never claims a fresher time than what
 * is drawn.
 */
export function staleSince(queries: readonly StaleQuery[]): number | null {
  const times = queries.filter((query) => query.isRefetchError && query.dataUpdatedAt > 0).map((query) => query.dataUpdatedAt);
  return times.length === 0 ? null : Math.min(...times);
}
