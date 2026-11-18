import { describe, expect, it } from 'vitest';

import { collectPlugins, plugins } from './index';

describe('plugin slot', () => {
  it('finds no plugin in the Community Edition', () => {
    expect(plugins).toEqual([]);
  });

  it('collects the default export of every module, ordered by path', () => {
    const found = collectPlugins({
      './zeta/index.ts': { default: { name: 'zeta' } },
      './alpha/index.ts': { default: { name: 'alpha' } },
    });
    expect(found.map((plugin) => plugin.name)).toEqual(['alpha', 'zeta']);
  });
});
