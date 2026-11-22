/**
 * The 30-day strip of a job: one cell per local calendar day, the worst run
 * planned that day (docs/evaluator.md states), today on the right. Pure, so
 * it is tested as data.
 */
import type { OccurrenceState } from '../../api/dashboard';
import type { OccurrenceOut } from '../../api/jobs';
import { worstOf } from '../../ribbon/ribbonLayout';

export interface StripCell {
  /** YYYY-MM-DD in the browser's zone. */
  readonly date: string;
  readonly state: OccurrenceState | null;
  readonly runs: number;
  readonly today: boolean;
}

function dateKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** The first instant of the day `daysAgo` days before `now`, local time. */
export function startOfDayAgo(now: Date, daysAgo: number): Date {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  date.setDate(date.getDate() - daysAgo);
  return date;
}

export function stripCells(occurrences: readonly OccurrenceOut[], now: Date, days = 30): readonly StripCell[] {
  const byDay = new Map<string, OccurrenceState[]>();
  for (const occurrence of occurrences) {
    const at = new Date(occurrence.scheduled_for);
    if (Number.isNaN(at.getTime())) {
      continue;
    }
    const key = dateKey(at);
    const list = byDay.get(key) ?? [];
    list.push(occurrence.state);
    byDay.set(key, list);
  }
  const todayKey = dateKey(now);
  const cells: StripCell[] = [];
  for (let back = days - 1; back >= 0; back -= 1) {
    const key = dateKey(startOfDayAgo(now, back));
    const states = byDay.get(key) ?? [];
    cells.push({ date: key, state: worstOf(states), runs: states.length, today: key === todayKey });
  }
  return cells;
}
