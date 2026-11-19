import { expect, test } from '@playwright/test';

import { SCHEMES, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi } from './helpers';

// First run is open only while no account exists; the test build stubs the
// setup state. On Development the seed closes it, so the same URL is a 404.
for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`first run (open) at ${width} px, ${scheme}`, async ({ page }) => {
      await stubApi(page, { needsFirstRun: true });
      await setView(page, width, scheme);
      await page.goto('/first-run');
      await expect(page.getByRole('heading', { level: 1, name: 'Create the first admin' })).toBeVisible();
      await expectLogo(page, 'Checkorca-CE', 120);
      await expect(page.getByLabel('Repeat the password')).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('first-run', width, scheme), fullPage: true });
    });
  }
}

test('first run (closed) shows the 404 state', async ({ page }) => {
  await stubApi(page, { needsFirstRun: false });
  await setView(page, 1440, 'light');
  await page.goto('/first-run');
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
  await expect(page.getByText('First run is closed')).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/first-run-closed-1440-light.png', fullPage: true });
});

test('first run validates the passwords before sending', async ({ page }) => {
  await stubApi(page, { needsFirstRun: true });
  await setView(page, 768, 'dark');
  await page.goto('/first-run');
  await page.getByLabel('E-mail address').fill('owner@example.com');
  await page.getByLabel('Password', { exact: true }).fill('short');
  await page.getByLabel('Repeat the password').fill('short');
  await page.getByRole('button', { name: 'Create account and sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('at least 12 characters');
  await page.getByLabel('Password', { exact: true }).fill('long-enough-password');
  await page.getByLabel('Repeat the password').fill('long-enough-passw0rd');
  await page.getByRole('button', { name: 'Create account and sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('differ');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/first-run-error-768-dark.png', fullPage: true });
});
