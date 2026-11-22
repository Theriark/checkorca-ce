import { describe, expect, it } from 'vitest';

import { staleSince } from './staleSince';

describe('staleSince', () => {
  it('is null while no query failed to refresh', () => {
    expect(staleSince([])).toBeNull();
    expect(staleSince([{ isRefetchError: false, dataUpdatedAt: 1_000 }])).toBeNull();
  });

  it('ignores a failed query that never had data (a first-load error is not stale data)', () => {
    expect(staleSince([{ isRefetchError: true, dataUpdatedAt: 0 }])).toBeNull();
  });

  it('names the oldest data among the queries whose refresh failed, not a fresh one', () => {
    const queries = [
      { isRefetchError: false, dataUpdatedAt: 100 },
      { isRefetchError: true, dataUpdatedAt: 300 },
      { isRefetchError: true, dataUpdatedAt: 200 },
    ];
    expect(staleSince(queries)).toBe(200);
  });
});
