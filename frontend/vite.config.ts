import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Never inline an asset as a data: URL. The server sends a Content Security
    // Policy with font-src 'self' (and no data:), so an inlined font subset is
    // blocked with a console error on the live site. Every font and image is a
    // file under dist/assets instead; check-product-bundle.mjs enforces it.
    assetsInlineLimit: 0,
    // One entry, index.html. The backend answers every path outside /api/ that
    // is not a built file with it (app/web.py), so deep links boot the app.
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    css: false,
  },
});
