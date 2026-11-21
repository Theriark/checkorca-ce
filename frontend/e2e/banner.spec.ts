import { expect, test } from '@playwright/test';

import { installFakeApi, installIngestApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`stale-heartbeat banner on every signed-in screen at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN, workerStale: true });
      await installFakeApi(page);
      await installIngestApi(page);
      await setView(page, width, scheme);
      await page.goto('/clients');
      const banner = page.getByTestId('stale-worker-banner');
      await expect(banner).toBeVisible();
      // The fixed sentence is the alert; the changing age sits outside it.
      await expect(banner.getByRole('alert')).toContainText('The worker is not running');
      await expect(banner.getByRole('alert')).not.toContainText('22 minutes');
      await expect(banner).toContainText('No heartbeat for 22 minutes.');
      await expect(banner.locator('svg')).toHaveCount(1);
      // Signal red fill with light text.
      expect(await banner.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe('rgb(208, 32, 42)');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('banner', width, scheme), fullPage: false });
      // It stays on every section, built or placeholder, and on a detail page.
      for (const path of ['/', '/inboxes', '/messages', '/system']) {
        await page.goto(path);
        await expect(page.getByTestId('stale-worker-banner')).toBeVisible();
      }
      expect(errors()).toEqual([]);
    });
  }
}

test('banner: nothing while the worker ticks, and the technician sees it too', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installFakeApi(page);
  await installIngestApi(page);
  await setView(page, 768, 'light');
  await page.goto('/inboxes');
  await expect(page.getByRole('heading', { level: 1, name: 'Inboxes' })).toBeVisible();
  await expect(page.getByTestId('stale-worker-banner')).toHaveCount(0);
  await stubApi(page, { me: TECHNICIAN, workerStale: true });
  await page.goto('/jobs');
  await expect(page.getByTestId('stale-worker-banner')).toBeVisible();
  await expectAccessible(page);
});

test('banner: never on the sign-in page', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: null, workerStale: true });
  await setView(page, 390, 'dark');
  await page.goto('/login');
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
  await expect(page.getByTestId('stale-worker-banner')).toHaveCount(0);
  expect(errors()).toEqual([]);
});
