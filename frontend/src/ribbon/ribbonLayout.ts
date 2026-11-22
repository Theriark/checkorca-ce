/**
 * Pure geometry and grouping of the live Night Ribbon (docs/dashboard.md,
 * dashboard/ribbon): the time scale of the window, the ring kind of each
 * occurrence state, the rows (one per client, every job's runs on that line)
 * and the hour ticks of the axis. No DOM here, so it is unit tested as data.
 */
import type { OccurrenceState, Ribbon, RibbonClient, RibbonOccurrence, RibbonWindow } from '../api/dashboard';

export const RING_RADIUS = 7;
/** Space left of the first and right of the last instant of the window. */
export const RIBBON_PAD = 12;
export const ROW_HEIGHT = 36;
export const AXIS_HEIGHT = 26;

export type RingKind = 'verified' | 'warning' | 'failed' | 'hollow' | 'pending' | 'running' | 'maintenance';

/** A hollow ring is an overdue or missed run: silence made visible. */
export function isSilent(state: OccurrenceState): boolean {
  return state === 'overdue' || state === 'missed';
}

export function isProblem(state: OccurrenceState): boolean {
  return state === 'warning' || state === 'failed' || isSilent(state);
}

export function ringKind(state: OccurrenceState): RingKind {
  switch (state) {
    case 'verified':
      return 'verified';
    case 'warning':
      return 'warning';
    case 'failed':
      return 'failed';
    case 'overdue':
    case 'missed':
      return 'hollow';
    case 'running':
      return 'running';
    case 'maintenance':
      return 'maintenance';
    default:
      return 'pending';
  }
}

/** Worse first: the order of chips and of the worst state of a day. */
export const STATE_RANK: Record<OccurrenceState, number> = {
  missed: 7,
  failed: 6,
  overdue: 5,
  warning: 4,
  running: 3,
  pending: 2,
  verified: 1,
  maintenance: 0,
};

export function worstOf(states: readonly OccurrenceState[]): OccurrenceState | null {
  let worst: OccurrenceState | null = null;
  for (const state of states) {
    if (worst === null || STATE_RANK[state] > STATE_RANK[worst]) {
      worst = state;
    }
  }
  return worst;
}

export interface Scale {
  readonly from: number;
  readonly to: number;
  readonly width: number;
  /** The x of an instant, clamped to the drawing. */
  readonly x: (iso: string) => number;
}

export function makeScale(window: RibbonWindow, width: number): Scale {
  const from = Date.parse(window.from);
  const to = Date.parse(window.to);
  const span = Math.max(to - from, 1);
  const inner = Math.max(width - 2 * RIBBON_PAD, 1);
  return {
    from,
    to,
    width,
    x: (iso) => {
      const at = Date.parse(iso);
      if (Number.isNaN(at)) {
        return RIBBON_PAD;
      }
      const ratio = Math.min(Math.max((at - from) / span, 0), 1);
      return Math.round((RIBBON_PAD + ratio * inner) * 10) / 10;
    },
  };
}

export interface RibbonRun {
  readonly clientId: string;
  readonly clientName: string;
  readonly jobId: string;
  readonly jobName: string;
  readonly occurrence: RibbonOccurrence;
}

export interface RibbonRow {
  readonly client: RibbonClient;
  /** By planned time. */
  readonly runs: readonly RibbonRun[];
}

/** One row per client with every run of its jobs on that line, by time. */
export function rowsOf(ribbon: Ribbon): readonly RibbonRow[] {
  return ribbon.clients.map((client) => ({
    client,
    runs: client.jobs
      .flatMap((job) => job.occurrences.map((occurrence) => ({ clientId: client.id, clientName: client.name, jobId: job.id, jobName: job.name, occurrence })))
      .sort((a, b) => a.occurrence.scheduled_for.localeCompare(b.occurrence.scheduled_for)),
  }));
}

export interface RibbonCounts {
  readonly clients: number;
  readonly jobs: number;
  readonly runs: number;
  readonly problems: number;
  readonly silent: number;
}

export function countsOf(ribbon: Ribbon): RibbonCounts {
  let jobs = 0;
  let runs = 0;
  let problems = 0;
  let silent = 0;
  for (const client of ribbon.clients) {
    jobs += client.jobs.length;
    for (const job of client.jobs) {
      for (const occurrence of job.occurrences) {
        runs += 1;
        if (isProblem(occurrence.state)) {
          problems += 1;
        }
        if (isSilent(occurrence.state)) {
          silent += 1;
        }
      }
    }
  }
  return { clients: ribbon.clients.length, jobs, runs, problems, silent };
}

/** Rings closer than a diameter on one line are nudged off the centre line
 *  (0, then -1, then +1 lanes) so none hides another. */
export function lanesOf(xs: readonly number[]): readonly number[] {
  const lanes: number[] = [];
  let lastX = Number.NEGATIVE_INFINITY;
  let turn = 0;
  for (const x of xs) {
    if (x - lastX < 2 * RING_RADIUS + 2) {
      turn = (turn + 1) % 3;
    } else {
      turn = 0;
    }
    lanes.push(turn === 0 ? 0 : turn === 1 ? -1 : 1);
    lastX = x;
  }
  return lanes;
}

export interface Tick {
  readonly iso: string;
  readonly at: number;
}

/** Whole local hours divisible by the step inside the window, oldest first. */
export function hourTicks(window: RibbonWindow, stepHours = 3): readonly Tick[] {
  const from = Date.parse(window.from);
  const to = Date.parse(window.to);
  if (Number.isNaN(from) || Number.isNaN(to) || to <= from) {
    return [];
  }
  const cursor = new Date(from);
  cursor.setMinutes(0, 0, 0);
  let guard = 0;
  while ((cursor.getTime() < from || cursor.getHours() % stepHours !== 0) && guard < 48) {
    cursor.setHours(cursor.getHours() + 1);
    guard += 1;
  }
  const ticks: Tick[] = [];
  while (cursor.getTime() < to && ticks.length < 100) {
    ticks.push({ iso: cursor.toISOString(), at: cursor.getTime() });
    cursor.setHours(cursor.getHours() + stepHours);
  }
  return ticks;
}

/** True when the instant lies inside [from, to). */
export function inWindow(window: RibbonWindow, at: Date): boolean {
  const time = at.getTime();
  return time >= Date.parse(window.from) && time < Date.parse(window.to);
}
