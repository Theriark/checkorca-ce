import { describe, expect, it } from 'vitest';

import { namesMatch, parseAliases } from './clientForm';

describe('client form', () => {
  it('reads aliases one per line and drops blanks', () => {
    expect(parseAliases('Harbourside\n  HD Clinic \n\n')).toEqual(['Harbourside', 'HD Clinic']);
    expect(parseAliases('')).toEqual([]);
  });

  it('matches the typed name like the server: trimmed, runs of spaces collapsed, case kept', () => {
    expect(namesMatch('  Harbourside   Dental ', 'Harbourside Dental')).toBe(true);
    expect(namesMatch('harbourside dental', 'Harbourside Dental')).toBe(false);
    expect(namesMatch('Harbourside', 'Harbourside Dental')).toBe(false);
  });
});
