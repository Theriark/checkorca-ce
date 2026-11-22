import { describe, expect, it } from 'vitest';

import { fill, formatAgo, formatDate, formatDateTime, formatShortDateTime, formatTime, formatUtcTime, localInputToIso, nowForLocalInput, toDateInputValue } from './format';

describe('format', () => {
  it('formats an instant in a given zone, day first, 24-hour clock', () => {
    expect(formatDateTime('2026-11-19T23:00:00Z', 'Europe/Lisbon')).toBe('Thu, 19 Nov 2026, 23:00');
    expect(formatDateTime('2026-11-19T23:00:00Z', 'America/New_York')).toBe('Thu, 19 Nov 2026, 18:00');
    // An unknown zone falls back to the browser's zone instead of throwing.
    expect(formatDateTime('2026-11-19T23:00:00Z', 'Mars/Olympus')).toMatch(/19 Nov 2026/);
    expect(formatDateTime('not a date')).toBe('not a date');
  });

  it('formats dates and UTC times', () => {
    expect(formatDate('2026-11-01T09:00:00Z')).toBe('1 Nov 2026');
    expect(formatUtcTime('2026-11-19T23:00:00Z')).toBe('23:00 UTC');
    expect(formatUtcTime('bad')).toBe('bad');
  });

  it('turns a datetime-local value into an ISO instant, or null', () => {
    expect(localInputToIso('')).toBeNull();
    expect(localInputToIso('not-a-time')).toBeNull();
    const iso = localInputToIso('2027-01-05T09:30');
    expect(iso).toMatch(/^2027-01-05T\d\d:\d\d:00\.000Z$/);
    expect(nowForLocalInput(new Date(2026, 10, 19, 8, 5))).toBe('2026-11-19T08:05');
  });

  it('says how long ago in the largest whole unit, or how far ahead', () => {
    const now = new Date('2026-11-20T08:00:00Z');
    expect(formatAgo('2026-11-20T07:59:30Z', now)).toBe('just now');
    expect(formatAgo('2026-11-20T07:15:00Z', now)).toBe('45 min ago');
    expect(formatAgo('2026-11-20T05:00:00Z', now)).toBe('3 h ago');
    expect(formatAgo('2026-11-19T07:00:00Z', now)).toBe('1 day ago');
    expect(formatAgo('2026-11-10T07:00:00Z', now)).toBe('10 days ago');
    expect(formatAgo('2026-11-20T08:40:00Z', now)).toBe('in 40 min');
    expect(formatAgo('bad', now)).toBe('bad');
  });

  it('formats a clock time, a short date and time, and a date input value', () => {
    expect(formatTime('2026-11-19T23:05:00Z')).toMatch(/^\d\d:\d\d$/);
    expect(formatShortDateTime('2026-11-19T23:05:00Z')).toMatch(/Nov/);
    expect(formatShortDateTime('2026-11-19T23:05:00Z')).not.toContain('2026');
    expect(formatTime('bad')).toBe('bad');
    expect(toDateInputValue(new Date(2026, 10, 3))).toBe('2026-11-03');
  });

  it('fills placeholders and leaves unknown ones', () => {
    expect(fill('{count} jobs for {name}', { count: 3, name: 'x' })).toBe('3 jobs for x');
    expect(fill('{missing}', {})).toBe('{missing}');
  });
});
