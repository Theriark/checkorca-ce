import { expect, test } from '@playwright/test';

import { SCHEMES, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`login at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page);
      await setView(page, width, scheme);
      await page.goto('/login');
      await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
      // The stacked lockup, loaded from the brand folder, at least 120 px wide.
      await expectLogo(page, 'Checkorca-CE', 120);
      const logo = page.getByRole('img', { name: 'Checkorca-CE' }).first();
      await expect(logo).toHaveAttribute('src', new RegExp(scheme === 'dark' ? 'logo-stacked-dark-400x400' : 'logo-stacked-400x400'));
      // The brand file carries an opaque tile in the page colour: it sits on
      // the page, never inside the card, so no square shows behind the mark.
      const logoParent = await logo.evaluate((element) => element.parentElement?.className ?? '');
      expect(logoParent).toContain('co-auth__body');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('login', width, scheme), fullPage: true });
      expect(errors()).toEqual([]);
    });
  }
}

test('login hero: reported rings are filled, the silent ring is hollow (never colour alone)', async ({ page }) => {
  await stubApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/login');
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
  const ring = (kind: string) => page.locator(`.co-auth__panel .co-ribbon-mark .co-ribbon-mark__ring--${kind}`).first();
  await expect(ring('hollow')).toBeAttached();
  const style = (kind: string) => ring(kind).evaluate((element) => ({ fill: getComputedStyle(element).fill, stroke: getComputedStyle(element).stroke }));
  // The hero night carries verified and warning rings and one silent ring.
  const [verified, warning, hollow] = await Promise.all([style('verified'), style('warning'), style('hollow')]);
  expect(hollow.fill).toBe('rgba(0, 0, 0, 0)');
  expect(verified.fill).toBe(verified.stroke);
  for (const filled of [verified, warning]) {
    expect(filled.fill).not.toBe('rgba(0, 0, 0, 0)');
    expect(filled.fill).not.toBe('none');
  }
});

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

test('a deep link survives sign-in: /jobs anonymous becomes /login?redirect=/jobs and lands on /jobs', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { loginStatus: 200 });
  await setView(page, 1440, 'light');
  await page.goto('/jobs');
  await expect(page).toHaveURL(/\/login\?redirect=%2Fjobs$/);
  await page.getByLabel('E-mail address').fill('checkorca.admin@example.com');
  await page.getByLabel('Password', { exact: true }).fill('the-right-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Jobs' })).toBeVisible();
  expect(errors()).toEqual([]);
});

test('a redirect that leaves the origin is dropped before sign-in', async ({ page }) => {
  await stubApi(page, { loginStatus: 200 });
  await setView(page, 1440, 'light');
  await page.goto('/login?redirect=%2F%2Fevil.example');
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
