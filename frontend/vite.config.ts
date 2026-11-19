import { resolve } from 'node:path';

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
    rollupOptions: {
      // 404.html is the same app: StaticFiles(html=True) serves it for deep
      // links (see 404.html).
      input: {
        main: resolve(__dirname, 'index.html'),
        notFound: resolve(__dirname, '404.html'),
      },
    },
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
