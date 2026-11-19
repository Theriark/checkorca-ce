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

  it('names the product in index.html and the web manifest', () => {
    const root = resolve(SRC, '..');
    const index = readFileSync(join(root, 'index.html'), 'utf8');
    // The product name reaches index.html and the manifest from this constant.
    expect(index).toContain(`<title>${PRODUCT_NAME}</title>`);
    expect(JSON.parse(readFileSync(join(root, 'public', 'manifest.webmanifest'), 'utf8')).name).toBe(PRODUCT_NAME);
  });

  it('keeps the gallery out of the product bundle: no static import, no gallery words in strings.ts', () => {
    const router = readFileSync(join(SRC, 'router.tsx'), 'utf8');
    expect(router).not.toMatch(/^import .*GalleryPage/m);
    const galleryRoute = readFileSync(join(SRC, 'routes', 'GalleryRoute.tsx'), 'utf8');
    expect(galleryRoute).not.toMatch(/^import .*GalleryPage/m);
    expect(galleryRoute).toContain("import('./GalleryPage')");
    const stringsSource = readFileSync(join(SRC, 'strings.ts'), 'utf8');
    expect(stringsSource).not.toContain('gallery');
    expect(readFileSync(join(SRC, 'routes', 'routes.css'), 'utf8')).not.toContain('co-gallery');
  });
});
