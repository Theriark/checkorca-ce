import { defineConfig, devices } from '@playwright/test';

// End-to-end tests against the production build served by vite preview, built
// with VITE_GALLERY=1 so the component gallery route exists (it never does in
// the product image). The preview has no backend: the specs stub the auth
// routes. Screenshots at 1440, 768 and 390 px go to screenshots/ (a CI
// artefact).
export default defineConfig({
  testDir: 'e2e',
  outputDir: 'test-results',
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 2,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build:e2e && npm run preview',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
