import { describe, expect, it } from 'vitest';

import { resolveRedirect, sanitiseRedirect } from './redirect';

describe('sanitiseRedirect (the router gate)', () => {
  it('keeps a plain same-origin path', () => {
    expect(sanitiseRedirect('/jobs')).toBe('/jobs');
    expect(sanitiseRedirect('/clients')).toBe('/clients');
  });

  it('drops anything that could leave the origin or carry a payload', () => {
    for (const hostile of [
      '//evil.example',
      '/\\evil.example',
      '/\\\\evil.example',
      'https://evil.example',
      'jobs',
      '',
      '/jobs?x=1',
      '/jobs#frag',
      '/jo bs',
      '/jobs\n',
      '/jobs\u0000',
      42,
      null,
      undefined,
      '/'.padEnd(600, 'a'),
    ]) {
      expect(sanitiseRedirect(hostile), String(hostile)).toBeUndefined();
    }
  });
});

describe('resolveRedirect (the login page gate)', () => {
  it('goes to a known section or plugin route, otherwise to the morning check', () => {
    expect(resolveRedirect('/jobs')).toBe('/jobs');
    expect(resolveRedirect('/settings')).toBe('/settings');
    expect(resolveRedirect('/reports', ['/reports'])).toBe('/reports');
    expect(resolveRedirect('/reports')).toBe('/');
    expect(resolveRedirect('/not-a-section')).toBe('/');
    expect(resolveRedirect('/jobs/123')).toBe('/');
    expect(resolveRedirect(undefined)).toBe('/');
  });
});
