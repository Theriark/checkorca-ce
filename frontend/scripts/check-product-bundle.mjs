#!/usr/bin/env node
/**
 * After a product build (npm run build, no VITE_GALLERY), proves that the
 * component gallery is not in the bundle: no gallery page, demo rows, words
 * or stylesheet in any file under dist/. Exits 1 with the offending file and
 * marker otherwise. The Docker image build runs it (Dockerfile: npm run build).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const DIST = resolve(process.argv[2] ?? 'dist');
const MARKERS = ['Component gallery', 'co-gallery', 'Harbourside Dental', 'Test build only'];

function files(folder) {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    return statSync(path).isDirectory() ? files(path) : /\.(js|css|html)$/.test(name) ? [path] : [];
  });
}

let checked = 0;
const offenders = [];
for (const path of files(DIST)) {
  checked += 1;
  const text = readFileSync(path, 'utf8');
  for (const marker of MARKERS) {
    if (text.includes(marker)) {
      offenders.push(`${relative(DIST, path)}: "${marker}"`);
    }
  }
}

if (checked === 0) {
  console.error(`check-product-bundle: no built files under ${DIST}`);
  process.exit(1);
}
if (offenders.length > 0) {
  console.error('check-product-bundle: the gallery leaked into the product bundle:');
  for (const line of offenders) {
    console.error(`  ${line}`);
  }
  process.exit(1);
}
console.log(`check-product-bundle: ${checked} built files, no gallery marker.`);
