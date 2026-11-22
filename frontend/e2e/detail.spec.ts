import { expect, test } from '@playwright/test';

import { HARBOURSIDE, installFakeApi, installIngestApi } from './fakeApi';
import { HOSTILE_CLIENT_NAME, HOSTILE_JOB_ID, HOSTILE_JOB_NAME, installDashboardApi } from './fakeDashboard';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`job detail at ${width} px, ${scheme}: state, 30-day strip, schedule, history, raw message as text`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      const fake = await installFakeApi(page);
      await installIngestApi(page);
      await installDashboardApi(page, { fake });
      await setView(page, width, scheme);
      await page.goto(`/jobs/${HOSTILE_JOB_ID}`);
      await expect(page.getByRole('heading', { level: 1, name: HOSTILE_JOB_NAME })).toBeVisible();
      await expect(page.getByRole('link', { name: HOSTILE_CLIENT_NAME })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Acknowledge' })).toBeVisible();
      await expect(page.getByText('Not acknowledged')).toBeVisible();
      // The strip: 30 cells, the last marked as today; icons in the cells.
      const strip = page.getByTestId('day-strip');
      await expect(strip.locator('.co-strip__cell')).toHaveCount(30);
      await expect(strip.locator('.co-strip__cell--today')).toHaveCount(1);
      await expect(strip.locator('.co-strip__cell[data-state="missed"] svg')).toHaveCount(1);
      expect(await strip.locator('.co-strip__cell[data-state="failed"]').count()).toBeGreaterThan(0);
      // Schedule and history.
      await expect(page.getByText('Europe/Lisbon')).toBeVisible();
      const runs = page.getByRole('table', { name: 'Runs' });
      await expect(runs.locator('tbody tr')).toHaveCount(30);
      await expect(runs.locator('tbody tr').first()).toHaveAttribute('data-state', 'missed');
      await page.getByRole('tab', { name: /State changes/ }).click();
      await expect(page.getByRole('table', { name: 'State changes' }).locator('tbody tr')).toHaveCount(2);
      // The raw message: literal tags, no element created, nothing ran.
      const raw = page.getByTestId('job-raw-message');
      await expect(raw).toContainText('<script>window.__pwned = 6</script>');
      await expect(raw).toContainText('<a href="javascript:window.__pwned = 8">open</a>');
      expect(await raw.locator('script, img, a').count()).toBe(0);
      expect(await page.locator('script:not([src])').count()).toBe(0);
      expect(await page.locator('img[onerror], a[href^="javascript:"]').count()).toBe(0);
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      expect(await raw.evaluate((element) => getComputedStyle(element).fontFamily)).toMatch(/JetBrains Mono/);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('job-detail', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });

    test(`system at ${width} px, ${scheme}: worker, inboxes, queues, build`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await page.route('**/api/v1/system/status', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            worker: { heartbeat_at: new Date(Date.now() - 20_000).toISOString(), age_seconds: 20, stale: false, holder: 'worker-1:42', started_at: '2026-11-19T08:00:00Z' },
            inboxes: [
              { id: 'i1', kind: 'smtp', label: 'Veeam reports', last_message_at: '2026-11-19T23:05:00Z' },
              { id: 'i2', kind: 'webhook', label: 'Script <script>window.__pwned = 1</script> results', last_message_at: null },
            ],
            queue: { pending_messages: 2, pending_notifications: 0, failed_notifications: 0 },
            evaluator_lag_seconds: 0,
            version: '27.0.0',
            revision: 'e2e0000000000000000000000000000000000000',
            extension_api_level: 1,
          }),
        }),
      );
      await setView(page, width, scheme);
      await page.goto('/system');
      await expect(page.getByRole('heading', { level: 1, name: 'System' })).toBeVisible();
      await expect(page.getByTestId('worker-state')).toContainText('Ticking');
      await expect(page.getByTestId('evaluator-lag')).toContainText('Up to date');
      await expect(page.getByText('Veeam reports')).toBeVisible();
      await expect(page.getByText('Script <script>window.__pwned = 1</script> results')).toBeVisible();
      await expect(page.getByTestId('system-version')).toContainText('27.0.0');
      await expect(page.getByTestId('system-revision')).toContainText('e2e0000');
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('system', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
  test(`client detail at ${width} px, ${scheme}: the ribbon tab, the history tab and the history export`, async ({ page }) => {
    const errors = watchConsole(page);
    await stubApi(page, { me: ADMIN });
    const fake = await installFakeApi(page);
    const store = await installDashboardApi(page, { fake });
    await setView(page, width, scheme);
    await page.goto(`/clients/${HARBOURSIDE.id}`);
    await expect(page.getByRole('heading', { level: 1, name: HARBOURSIDE.name })).toBeVisible();
    await page.getByRole('tab', { name: 'Night Ribbon' }).click();
    if (width > 390) {
      const ribbon = page.getByTestId('night-ribbon');
      await expect(ribbon.locator('.co-nr__row-svg')).toHaveCount(1);
      await expect(ribbon.locator('.co-nr__ring--hollow')).toHaveCount(1);
      await expect(ribbon.locator('.co-nr__ring--verified')).toHaveCount(2);
    } else {
      await expect(page.getByTestId('ribbon-chips').locator('.co-nrc__chip')).toHaveCount(4);
    }
    await expectAccessible(page);
    await page.screenshot({ path: shot('client-ribbon', width, scheme), fullPage: width > 390 });
    await page.getByRole('tab', { name: 'History' }).click();
    const history = page.getByRole('table', { name: 'History' });
    await expect(history.locator('tbody tr')).toHaveCount(1);
    await expect(history).toContainText('SQL dump script');
    await expect(history).toContainText('Finished with warnings');
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export history' }).click();
    expect((await download).suggestedFilename()).toBe(`client-${HARBOURSIDE.id}-history.csv`);
    expect(store.calls.some((call) => call.url === `/api/v1/clients/${HARBOURSIDE.id}/export.csv`)).toBe(true);
    await expect(page.locator('.co-toast--success').last()).toContainText('Export downloaded');
    expect(errors()).toEqual([]);
  });
}

test('jobs list links to the job detail; an unknown job shows the not-found state in the shell', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  const fake = await installFakeApi(page);
  await installDashboardApi(page, { fake });
  await setView(page, 1440, 'dark');
  await page.goto('/jobs');
  await page.getByRole('link', { name: 'Veeam nightly' }).click();
  await expect(page).toHaveURL(/\/jobs\/j1000000-0000-4000-8000-000000000001$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Veeam nightly' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'No run in the last 30 days' })).toBeVisible();
  await page.goto('/jobs/j1000000-0000-4000-8000-00000000ffff');
  await expect(page.getByRole('heading', { level: 1, name: 'Job not found' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'All jobs' })).toBeVisible();
  await expectAccessible(page);
});
