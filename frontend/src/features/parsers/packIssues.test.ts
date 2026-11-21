import { describe, expect, it } from 'vitest';

import { PACK_YAML } from '../../test/fixtures';
import { describePointer, locateIssue, pointerSegments } from './packIssues';
import { splitBySpans } from './spans';

describe('pack issue locations', () => {
  it('reads a JSON Pointer', () => {
    expect(pointerSegments('')).toEqual([]);
    expect(pointerSegments('/status_rules/2/regex')).toEqual(['status_rules', '2', 'regex']);
    expect(pointerSegments('/extract/details/a~1b~0c')).toEqual(['extract', 'details', 'a/b~c']);
    expect(describePointer('/status_rules/2/regex')).toBe('status_rules › 2 › regex');
  });

  it('finds the line of a top-level key, a nested key and a sequence item', () => {
    const lines = PACK_YAML.split('\n');
    expect(locateIssue(PACK_YAML, '')).toBeNull();
    expect(locateIssue(PACK_YAML, '/version')?.line).toBe(lines.indexOf('version: 3'));
    expect(locateIssue(PACK_YAML, '/extract/job_name/regex')?.line).toBe(lines.findIndex((line) => line.startsWith("    regex: '^(?P<job_name>")));
    expect(locateIssue(PACK_YAML, '/match/any/0/subject')?.line).toBe(lines.findIndex((line) => line.startsWith('    - subject:')));
    // A flow mapping on one line: the key resolves to the item line.
    expect(locateIssue(PACK_YAML, '/status_rules/1/regex')?.line).toBe(lines.findIndex((line) => line.startsWith('  - {status: success')));
    // The offsets cover the whole line.
    const where = locateIssue(PACK_YAML, '/version');
    expect(PACK_YAML.slice(where?.from, where?.to)).toBe('version: 3');
  });

  it('falls back to the deepest line it could follow', () => {
    const lines = PACK_YAML.split('\n');
    expect(locateIssue(PACK_YAML, '/extract/nothing/here')?.line).toBe(lines.indexOf('extract:'));
    expect(locateIssue(PACK_YAML, '/missing')).toBeNull();
  });
});

describe('spans', () => {
  it('cuts the text at the span edges, drops spans outside the text and keeps the first of two that overlap', () => {
    const text = 'Job: Nightly backup failed';
    const pieces = splitBySpans(text, [
      { start: 5, end: 19, field: 'job_name', result: 1 },
      { start: 20, end: 26, field: 'status', result: 1 },
      { start: 10, end: 15, field: 'details.x', result: 2 },
      { start: 30, end: 40, field: 'bad', result: 1 },
    ]);
    expect(pieces.map((piece) => [piece.text, piece.span?.field ?? null])).toEqual([
      ['Job: ', null],
      ['Nightly backup', 'job_name'],
      [' ', null],
      ['failed', 'status'],
    ]);
    expect(splitBySpans('', [])).toEqual([]);
  });

  it('counts the offsets in code points as the engine does, so a span after an emoji still lands on its value', () => {
    // "Status 🔴 Job: Nightly file backup": the emoji is one code point and two string units.
    const text = 'Status \u{1F534} Job: Nightly file backup';
    const pieces = splitBySpans(text, [
      { start: 7, end: 8, field: 'status', result: 1 },
      { start: 14, end: 33, field: 'job_name', result: 1 },
    ]);
    expect(pieces.map((piece) => [piece.text, piece.span?.field ?? null])).toEqual([
      ['Status ', null],
      ['\u{1F534}', 'status'],
      [' Job: ', null],
      ['Nightly file backup', 'job_name'],
    ]);
    // A span that ends at the last code point is kept; one past it is dropped.
    expect(splitBySpans('a\u{1F534}', [{ start: 1, end: 2, field: 'x', result: 1 }]).map((piece) => piece.text)).toEqual(['a', '\u{1F534}']);
    expect(splitBySpans('a\u{1F534}', [{ start: 1, end: 3, field: 'x', result: 1 }]).map((piece) => piece.text)).toEqual(['a\u{1F534}']);
  });
});
