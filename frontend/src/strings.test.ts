import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import manifest from '../package.json';
import { APP_VERSION, PRODUCT_NAME } from './strings';

const SRC = resolve(__dirname);

function sourceFiles(folder: string): string[] {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) {
      return sourceFiles(path);
    }
    return /\.(ts|tsx|css)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe('strings', () => {
  it('keeps the version equal to package.json', () => {
    expect(APP_VERSION).toBe(manifest.version);
  });

  it('writes the product name in one constant only (rename risk N-1)', () => {
    const offenders = sourceFiles(SRC)
      .filter((path) => relative(SRC, path) !== 'strings.ts' && relative(SRC, path) !== 'api/schema.d.ts')
      .filter((path) => readFileSync(path, 'utf8').includes(PRODUCT_NAME));
    expect(offenders.map((path) => relative(SRC, path))).toEqual([]);
  });

  it('uses the full product name', () => {
    expect(PRODUCT_NAME).toBe('Checkorca-CE');
  });
});
