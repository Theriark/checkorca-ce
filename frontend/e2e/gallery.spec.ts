import { expect, test } from '@playwright/test';

import { SCHEMES, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi } from './helpers';

// The component gallery exists in the test build only (VITE_GALLERY=1).
for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`gallery at ${width} px, ${scheme}: every component state passes axe`, async ({ page }) => {
      await stubApi(page);
      await setView(page, width, scheme);
      await page.goto('/_gallery');
      await expect(page.getByRole('heading', { level: 1, name: 'Component gallery' })).toBeVisible();
      // Every section rendered.
      for (const id of ['buttons', 'fields', 'badges', 'stats', 'coverage', 'skeleton', 'states', 'table', 'overlays', 'ribbon']) {
        await expect(page.locator(`#${id}`)).toBeVisible();
      }
      // Status badges: icon plus word, all nine states.
      await expect(page.locator('#badges .co-badge')).toHaveCount(12);
      await expect(page.locator('#badges .co-badge svg')).toHaveCount(12);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('gallery', width, scheme), fullPage: true });
    });
  }
}

test('gallery overlays: dialog traps focus, toast announces, command search filters', async ({ page }) => {
  await stubApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/_gallery');

  await page.getByRole('button', { name: 'Open dialog' }).click();
  const dialog = page.getByRole('dialog', { name: 'Pause job' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Until')).toBeFocused();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/gallery-dialog-1440-light.png' });
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();

  await page.getByRole('button', { name: 'Error toast' }).click();
  await expect(page.locator('.co-toast--danger')).toContainText('Failed');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/gallery-toast-1440-light.png' });

  await page.getByRole('button', { name: 'Open command search' }).click();
  const input = page.getByRole('combobox', { name: 'Command search' });
  await expect(input).toBeFocused();
  await input.fill('jo');
  await expect(page.getByRole('option')).toHaveCount(1);
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/gallery-command-1440-light.png' });
});

test('gallery table: sort, density and a saved view', async ({ page }) => {
  await stubApi(page);
  await setView(page, 1440, 'dark');
  await page.goto('/_gallery');
  const table = page.locator('#table').first();
  const header = table.getByRole('columnheader', { name: /Runs/ }).first();
  await header.getByRole('button').click();
  await expect(header).toHaveAttribute('aria-sort', 'ascending');
  await table.getByRole('button', { name: 'Compact' }).first().click();
  await expect(table.locator('.co-table-wrap--compact').first()).toBeVisible();
  await table.getByRole('button', { name: 'Save view' }).first().click();
  await page.getByLabel('View name').fill('Fewest runs');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(table.getByRole('combobox', { name: 'Saved views' }).first()).toContainText('Fewest runs');
  await page.screenshot({ path: 'screenshots/gallery-table-1440-dark.png' });
});
