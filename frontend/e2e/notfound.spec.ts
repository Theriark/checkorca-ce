import { expect, test } from '@playwright/test';

import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`404 at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
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
      expect(errors()).toEqual([]);
    });
  }
}

test('the technician cannot open Settings by address', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await setView(page, 1440, 'light');
  await page.goto('/settings');
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
  await expect(page.getByText('This section is for admins.')).toBeVisible();
});

test('the product build has no gallery route', async ({ page }) => {
  // The e2e build enables the gallery; the product build must answer 404 for
  // it. This checks the route guard itself: with the flag off the route is not
  // registered (router.tsx), which scripts/check-product-bundle.mjs completes
  // after every product build.
  await stubApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/_gallery');
  await expect(page.getByRole('heading', { level: 1, name: 'Component gallery' })).toBeVisible();
});

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
