import { expect, test } from '@playwright/test';

import { installFakeApi, installIngestApi, installParserApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectLogo, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

const SECTIONS = ['Morning check', 'Clients', 'Jobs', 'Unmatched', 'Inboxes', 'Parsers', 'Notifications', 'System', 'Settings'];
// Sections with a built page (C3, C4, C5); the others still show their placeholder.
const BUILT = ['Clients', 'Jobs', 'Unmatched', 'Inboxes', 'Parsers'];

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`shell as admin at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await setView(page, width, scheme);
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
      await expectLogo(page, 'Checkorca-CE', 120);
      const logo = page.getByRole('img', { name: 'Checkorca-CE' }).first();
      await expect(logo).toHaveAttribute('src', new RegExp(scheme === 'dark' ? 'logo-horizontal-dark-600x200' : 'logo-horizontal-600x200'));

      const sidebar = page.getByRole('navigation', { name: 'Main navigation' });
      const bottom = page.getByRole('navigation', { name: 'Quick navigation' });
      if (width === 390) {
        await expect(sidebar).toBeHidden();
        await expect(bottom).toBeVisible();
        await expect(bottom.getByRole('link')).toHaveCount(4);
        await expect(bottom.getByRole('button', { name: 'More' })).toBeVisible();
        // Every bottom bar label fits on one line.
        for (const label of await bottom.locator('.co-nav__label').all()) {
          const [height, lineHeight] = await label.evaluate((element) => [element.getBoundingClientRect().height, parseFloat(getComputedStyle(element).lineHeight)]);
          expect(height).toBeLessThan(lineHeight * 1.5);
        }
      } else {
        await expect(bottom).toBeHidden();
        await expect(sidebar).toBeVisible();
        for (const section of SECTIONS) {
          await expect(sidebar.getByRole('link', { name: section })).toBeVisible();
        }
        await expect(sidebar.getByRole('link', { name: 'Morning check' })).toHaveAttribute('aria-current', 'page');
      }
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('shell-admin', width, scheme), fullPage: true });
      expect(errors()).toEqual([]);
    });

    test(`shell as technician at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: TECHNICIAN });
      await installFakeApi(page);
      await setView(page, width, scheme);
      await page.goto('/jobs');
      await expect(page.getByRole('heading', { level: 1, name: 'Jobs' })).toBeVisible();
      await expect(page.getByRole('table', { name: 'Jobs with their schedule and state' })).toBeVisible();
      if (width !== 390) {
        const sidebar = page.getByRole('navigation', { name: 'Main navigation' });
        await expect(sidebar.getByRole('link', { name: 'Settings' })).toHaveCount(0);
        await expect(sidebar.getByRole('link', { name: 'Jobs' })).toHaveAttribute('aria-current', 'page');
      }
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('shell-technician', width, scheme), fullPage: true });
      expect(errors()).toEqual([]);
    });
  }
}

test('shell: every section link opens its page or a designed placeholder, never a blank page', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const fake = await installFakeApi(page);
  const ingest = await installIngestApi(page);
  await installParserApi(page, { fake, ingest });
  await setView(page, 1440, 'light');
  await page.goto('/');
  const sidebar = page.getByRole('navigation', { name: 'Main navigation' });
  for (const section of SECTIONS) {
    await sidebar.getByRole('link', { name: section }).click();
    await expect(page.getByRole('heading', { level: 1, name: section })).toBeVisible();
    if (section === 'Unmatched') {
      // A queue and a split view, not a table.
      await expect(page.getByRole('list', { name: 'Unmatched results' })).toBeVisible();
    } else if (BUILT.includes(section)) {
      await expect(page.getByRole('table')).toBeVisible();
    } else {
      await expect(page.getByText(/Arrives in phase C\d+/)).toBeVisible();
    }
  }
});

test('shell at 390: the More sheet lists the other sections and the theme toggle', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await setView(page, 390, 'dark');
  await page.goto('/');
  await page.getByRole('button', { name: 'More' }).click();
  const sheet = page.getByRole('dialog', { name: 'Sections' });
  await expect(sheet).toBeVisible();
  for (const section of ['Inboxes', 'Parsers', 'Notifications', 'System', 'Settings']) {
    await expect(sheet.getByRole('link', { name: section })).toBeVisible();
  }
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/shell-more-390-dark.png' });
  await sheet.getByRole('link', { name: 'System' }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByRole('heading', { level: 1, name: 'System' })).toBeVisible();
});

test('shell: user menu shows the account and signs out; theme toggle switches', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await setView(page, 1440, 'light');
  await page.goto('/');
  await page.getByRole('button', { name: 'Dark theme' }).first().click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: /Account menu/ }).click();
  const menu = page.getByRole('menu');
  await expect(menu).toContainText(ADMIN.email);
  await expect(menu).toContainText('Admin');
  await page.screenshot({ path: 'screenshots/shell-usermenu-1440-dark.png' });
  await stubApi(page, { me: null });
  await menu.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test('shell: Ctrl K opens the command search and goes to Clients', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
  await page.keyboard.press('Control+k');
  const input = page.getByRole('combobox', { name: 'Command search' });
  await expect(input).toBeFocused();
  await input.fill('cli');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/clients$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible();
});

test('shell: no console errors while signed in and moving between sections', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Clients' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible();
  expect(errors()).toEqual([]);
});

test('shell: a failed sign-out keeps the session and says so', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await page.route('**/api/v1/auth/logout', (route) =>
    route.fulfill({ status: 503, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Service Unavailable', status: 503 }) }),
  );
  await setView(page, 1440, 'light');
  await page.goto('/');
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('menu').getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page.locator('.co-toast--danger')).toContainText('still signed in');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
});
