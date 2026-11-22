import { describe, expect, it } from 'vitest';

import { EMPTY_RIBBON, makeRibbon } from '../test/fixtures';
import { RIBBON_PAD, RING_RADIUS, countsOf, hourTicks, inWindow, isProblem, isSilent, lanesOf, makeScale, ringKind, rowsOf, worstOf } from './ribbonLayout';

const WINDOW = { from: '2026-11-19T18:00:00Z', to: '2026-11-20T12:00:00Z' };

describe('ribbon layout', () => {
  it('maps instants to x across the window, clamped at both ends', () => {
    const scale = makeScale(WINDOW, 412);
    expect(scale.x(WINDOW.from)).toBe(RIBBON_PAD);
    expect(scale.x(WINDOW.to)).toBe(412 - RIBBON_PAD);
    // 03:00 is the middle of an 18-hour night.
    expect(scale.x('2026-11-20T03:00:00Z')).toBe(206);
    expect(scale.x('2026-11-19T10:00:00Z')).toBe(RIBBON_PAD);
    expect(scale.x('2026-11-21T10:00:00Z')).toBe(412 - RIBBON_PAD);
    expect(scale.x('not a time')).toBe(RIBBON_PAD);
  });

  it('draws silence hollow and knows the problem states', () => {
    expect(ringKind('overdue')).toBe('hollow');
    expect(ringKind('missed')).toBe('hollow');
    expect(ringKind('verified')).toBe('verified');
    expect(ringKind('pending')).toBe('pending');
    expect(ringKind('running')).toBe('running');
    expect(isSilent('overdue')).toBe(true);
    expect(isSilent('failed')).toBe(false);
    expect(isProblem('warning')).toBe(true);
    expect(isProblem('verified')).toBe(false);
    expect(worstOf(['verified', 'warning', 'pending'])).toBe('warning');
    expect(worstOf(['overdue', 'failed'])).toBe('failed');
    expect(worstOf([])).toBeNull();
  });

  it('groups the runs of every job of a client on one row, by time, and counts them', () => {
    const rows = rowsOf(makeRibbon());
    expect(rows).toHaveLength(2);
    expect(rows[0]?.runs.map((run) => run.occurrence.scheduled_for)).toEqual(['2026-11-19T21:00:00Z', '2026-11-19T23:00:00Z', '2026-11-20T01:30:00Z', '2026-11-20T09:30:00Z']);
    expect(rows[0]?.runs[1]?.jobName).toContain('Veeam');
    expect(countsOf(makeRibbon())).toEqual({ clients: 2, jobs: 4, runs: 6, problems: 4, silent: 2 });
    expect(countsOf(EMPTY_RIBBON)).toEqual({ clients: 0, jobs: 0, runs: 0, problems: 0, silent: 0 });
  });

  it('nudges rings closer than a diameter off the line so none hides another', () => {
    const crowded = [100, 100 + RING_RADIUS, 100 + 2 * RING_RADIUS, 300];
    expect(lanesOf(crowded)).toEqual([0, -1, 1, 0]);
    expect(lanesOf([10, 60, 120])).toEqual([0, 0, 0]);
    expect(lanesOf([])).toEqual([]);
  });

  it('places whole-hour ticks every three hours inside the window', () => {
    const ticks = hourTicks(WINDOW, 3);
    expect(ticks.length).toBeGreaterThanOrEqual(5);
    expect(ticks.length).toBeLessThanOrEqual(7);
    for (const tick of ticks) {
      expect(tick.at).toBeGreaterThanOrEqual(Date.parse(WINDOW.from));
      expect(tick.at).toBeLessThan(Date.parse(WINDOW.to));
      expect(new Date(tick.iso).getMinutes()).toBe(0);
      expect(new Date(tick.iso).getHours() % 3).toBe(0);
    }
    expect(hourTicks({ from: WINDOW.to, to: WINDOW.from })).toEqual([]);
  });

  it('tells whether now is inside the window', () => {
    expect(inWindow(WINDOW, new Date('2026-11-20T08:00:00Z'))).toBe(true);
    expect(inWindow(WINDOW, new Date('2026-11-20T12:00:00Z'))).toBe(false);
    expect(inWindow(WINDOW, new Date('2026-11-19T17:59:00Z'))).toBe(false);
  });
});
