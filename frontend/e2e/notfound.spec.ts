import { expect, test } from '@playwright/test';

import { ADMIN, SCHEMES, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`404 at ${width} px, ${scheme}`, async ({ page }) => {
      await stubApi(page);
      await setView(page, width, scheme);
      await page.goto('/no-such-page');
      await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
      await expect(page.getByText('/no-such-page')).toBeVisible();
      await expect(page.getByRole('link', { name: 'Go to sign in' })).toBeVisible();
      await expectLogo(page, 'Checkorca-CE', 120);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('not-found', width, scheme), fullPage: true });
    });
  }
}

test('404 while signed in links back to the morning check', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await setView(page, 1440, 'light');
  await page.goto('/clients/missing');
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
  await page.getByRole('link', { name: 'Go to the morning check' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
});

test('the favicon and the web manifest are served', async ({ request }) => {
  const icon = await request.get('/brand/favicon-32x32.png');
  expect(icon.status()).toBe(200);
  expect(icon.headers()['content-type']).toContain('image/png');
  const manifest = await request.get('/manifest.webmanifest');
  expect(manifest.status()).toBe(200);
  expect((await manifest.json()).name).toBe('Checkorca-CE');
});
