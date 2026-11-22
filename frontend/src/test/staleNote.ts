import { expect } from 'vitest';

import { fill, formatTime } from '../lib/format';
import { strings } from '../strings';

/**
 * Asserts the stale note says the data is from a time between start (ms,
 * taken before the page rendered) and now: the receipt time of the last
 * good answer, to the minute.
 */
export function expectStaleNote(note: HTMLElement, start: number): void {
  const candidates = [formatTime(new Date(start).toISOString()), formatTime(new Date().toISOString())];
  const expected = candidates.map((time) => fill(strings.dashboard.staleData, { time }));
  expect(expected, `stale note "${note.textContent ?? ''}"`).toContain(note.textContent);
}
