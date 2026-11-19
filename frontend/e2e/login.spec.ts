import { expect, test } from '@playwright/test';

import { SCHEMES, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`login at ${width} px, ${scheme}`, async ({ page }) => {
      await stubApi(page);
      await setView(page, width, scheme);
      await page.goto('/login');
      await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
      // The stacked lockup, loaded from the brand folder, at least 120 px wide.
      await expectLogo(page, 'Checkorca-CE', 120);
      const logo = page.getByRole('img', { name: 'Checkorca-CE' }).first();
      await expect(logo).toHaveAttribute('src', new RegExp(scheme === 'dark' ? 'logo-stacked-dark-400x400' : 'logo-stacked-400x400'));
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('login', width, scheme), fullPage: true });
    });
  }
}

test('login focus order: e-mail, password, show password, sign in', async ({ page }) => {
  await stubApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/login');
  await page.getByLabel('E-mail address').focus();
  await expect(page.getByLabel('E-mail address')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Password', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Show password' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeFocused();
  // The focus ring is visible: a 2 px outline in the focus colour.
  const outline = await page.getByRole('button', { name: 'Sign in' }).evaluate((element) => getComputedStyle(element).outlineWidth);
  expect(outline).toBe('2px');
  await page.screenshot({ path: 'screenshots/login-focus-1440-light.png' });
});

test('login error states: wrong credentials, locked, rate limited', async ({ page }) => {
  await setView(page, 768, 'light');
  for (const [status, text] of [
    [401, 'do not match'],
    [423, 'locked'],
    [429, 'Too many attempts'],
  ] as const) {
    await stubApi(page, { loginStatus: status });
    await page.goto('/login');
    await page.getByLabel('E-mail address').fill('checkorca.admin@example.com');
    await page.getByLabel('Password', { exact: true }).fill('not-the-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toContainText(text);
    await expectAccessible(page);
    if (status === 401) {
      await page.screenshot({ path: 'screenshots/login-error-768-light.png', fullPage: true });
    }
  }
});

test('login succeeds and lands on the morning check', async ({ page }) => {
  await stubApi(page, { loginStatus: 200 });
  await setView(page, 1440, 'light');
  await page.goto('/login');
  await page.getByLabel('E-mail address').fill('checkorca.admin@example.com');
  await page.getByLabel('Password', { exact: true }).fill('the-right-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
});

test('login stays with the theme the user chose', async ({ page }) => {
  await stubApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/login');
  await page.getByRole('button', { name: 'Dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});
