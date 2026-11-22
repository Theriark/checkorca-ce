import { describe, expect, it } from 'vitest';

import { OCCURRENCES, makeOccurrence } from '../../test/fixtures';
import { startOfDayAgo, stripCells } from './dayStrip';

// Local midday, so the local day of every fixture is unambiguous in any zone
// the test runner happens to use.
const NOW = new Date(2026, 10, 20, 12, 0, 0);

describe('day strip', () => {
  it('builds 30 cells, oldest first, today last and marked', () => {
    const cells = stripCells(OCCURRENCES, NOW, 30);
    expect(cells).toHaveLength(30);
    expect(cells[29]?.today).toBe(true);
    expect(cells.filter((cell) => cell.today)).toHaveLength(1);
    expect(cells[0]?.date).toBe('2026-10-22');
    expect(cells[29]?.date).toBe('2026-11-20');
  });

  it('keeps the worst run of a day and counts the runs', () => {
    const twice = [makeOccurrence({ scheduled_for: '2026-11-18T10:00:00Z', state: 'verified' }), makeOccurrence({ scheduled_for: '2026-11-18T14:00:00Z', state: 'failed' })];
    const cells = stripCells(twice, NOW, 30);
    const day = cells.find((cell) => cell.date === '2026-11-18');
    expect(day?.state).toBe('failed');
    expect(day?.runs).toBe(2);
    expect(cells.find((cell) => cell.date === '2026-11-17')?.state).toBeNull();
  });

  it('ignores an occurrence it cannot date and handles no occurrences', () => {
    const cells = stripCells([makeOccurrence({ scheduled_for: 'bad' })], NOW, 7);
    expect(cells).toHaveLength(7);
    expect(cells.every((cell) => cell.state === null && cell.runs === 0)).toBe(true);
    expect(stripCells([], NOW, 1)[0]?.today).toBe(true);
  });

  it('starts a day at local midnight', () => {
    const start = startOfDayAgo(NOW, 0);
    expect(start.getHours()).toBe(0);
    expect(start.getDate()).toBe(20);
    expect(startOfDayAgo(NOW, 29).getDate()).toBe(22);
    expect(startOfDayAgo(NOW, -1).getDate()).toBe(21);
  });
});
