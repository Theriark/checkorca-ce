/** Whole minutes since the last heartbeat, at least 1 while stale. */
export function staleMinutes(ageSeconds: number | null): number {
  return ageSeconds === null ? 0 : Math.max(1, Math.floor(ageSeconds / 60));
}
