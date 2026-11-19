/** The editor's value of a schedule and its two directions: to the API's
 *  expression and back from a stored job. */
import type { ScheduleKind } from '../../api/jobs';

export interface ScheduleValue {
  readonly kind: ScheduleKind;
  /** The cron or interval expression. */
  readonly expr: string;
  /** The daily times, HH:MM each. */
  readonly times: readonly string[];
  readonly timezone: string;
}

/** The expression the API gets for the value. Daily times are joined the
 *  way the server stores them (comma, no space), so an unchanged job
 *  compares equal and sends no PATCH. */
export function scheduleExpression(value: ScheduleValue): string {
  if (value.kind === 'daily') {
    return value.times.map((time) => time.trim()).filter(Boolean).join(',');
  }
  return value.expr.trim();
}

/** The editor value for a stored job. */
export function scheduleValueOf(kind: ScheduleKind, expr: string, timezone: string): ScheduleValue {
  if (kind === 'daily') {
    const times = expr.split(',').map((time) => time.trim()).filter(Boolean);
    return { kind, expr: '', times: times.length > 0 ? times : [''], timezone };
  }
  return { kind, expr, times: ['23:00'], timezone };
}
