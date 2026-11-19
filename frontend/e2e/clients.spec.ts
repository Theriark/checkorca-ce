import { expect, test } from '@playwright/test';

import { HARBOURSIDE, installFakeApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`clients list and detail at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await installFakeApi(page);
      await setView(page, width, scheme);
      await page.goto('/clients');
      await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible();
      const table = page.getByRole('table', { name: 'Clients with their job counts and worst state' });
      await expect(table).toBeVisible();
      // Two live clients; the archived one is behind the toggle.
      await expect(table.locator('tbody tr')).toHaveCount(2);
      await expect(page.getByText('2 clients')).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      // Full page above the phone width; at 390 a full-page shot would paint
      // the fixed bottom bar mid-page, so the viewport is captured instead.
      await page.screenshot({ path: shot('clients', width, scheme), fullPage: width > 390 });

      await page.getByRole('link', { name: HARBOURSIDE.name }).click();
      await expect(page.getByRole('heading', { level: 1, name: HARBOURSIDE.name })).toBeVisible();
      await expect(page.getByRole('tab', { name: /Jobs/ })).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByRole('table', { name: 'Jobs with their schedule and state' }).locator('tbody tr')).toHaveCount(2);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('client-detail', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

test('clients: loading, empty and error states are designed', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await setView(page, 1440, 'light');
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/clients?**', async (route) => {
    await gate;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], next_cursor: null }) });
  });
  await page.goto('/clients');
  await expect(page.locator('tbody[aria-busy="true"]')).toBeVisible();
  release();
  await expect(page.getByRole('heading', { level: 3, name: 'No clients yet' })).toBeVisible();
  await expect(page.locator('.co-empty').getByRole('button', { name: 'New client' })).toBeVisible();
  await page.screenshot({ path: 'screenshots/clients-empty-1440-light.png' });

  await page.unroute('**/api/v1/clients?**');
  await page.route('**/api/v1/clients?**', (route) =>
    route.fulfill({ status: 500, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-e2e-500' }) }),
  );
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('The database did not answer in time.');
  await expect(page.getByRole('alert')).toContainText('req-e2e-500');
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('clients: search, status filter and the archived toggle', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await setView(page, 1440, 'dark');
  await page.goto('/clients');
  const rows = page.getByRole('table').locator('tbody tr');
  await expect(rows).toHaveCount(2);
  await page.getByRole('searchbox', { name: 'Search clients' }).fill('hd clinic');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText(HARBOURSIDE.name);
  await page.getByRole('searchbox', { name: 'Search clients' }).fill('');
  await expect(rows).toHaveCount(2);
  await page.getByRole('combobox', { name: 'Status' }).click();
  await page.getByRole('option', { name: 'Paused' }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('Northwind Legal (fictional)');
  await page.getByRole('combobox', { name: 'Status' }).click();
  await page.getByRole('option', { name: 'Any status' }).click();
  await page.getByRole('switch', { name: 'Show archived' }).check();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('Orchard Clinic (fictional)');
  await expect(rows.first()).toContainText('Archived');
});

// The dialog flows run on a desktop in light and on a phone in dark, so both
// themes of the create and delete dialogs are contrast-checked by axe.
for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
test(`clients: create a client, archive it, then delete it with the typed name (${width} px, ${scheme})`, async ({ page }) => {
  // The taken name and the wrong typed name are refused with 409 on purpose.
  const errors = watchConsole(page, [409]);
  await stubApi(page, { me: ADMIN });
  const store = await installFakeApi(page);
  await setView(page, width, scheme);
  await page.goto('/clients');
  await page.getByRole('button', { name: 'New client' }).click();
  const dialog = page.getByRole('dialog', { name: 'New client' });
  await expect(dialog.getByLabel('Name')).toBeFocused();
  // An empty name never reaches the server.
  await dialog.getByRole('button', { name: 'Create' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Enter a name.');
  // A taken name is a field error from the server's 409.
  await dialog.getByLabel('Name').fill(HARBOURSIDE.name);
  await dialog.getByRole('button', { name: 'Create' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Another client has this name.');
  await dialog.getByLabel('Name').fill('Blue Fern Studio (fictional)');
  await dialog.getByLabel(/Notes/).fill('Test client, synthetic.');
  await dialog.getByLabel(/Aliases/).fill('Blue Fern\nBFS');
  await expectAccessible(page);
  await page.screenshot({ path: shot('client-create', width, scheme) });
  await dialog.getByRole('button', { name: 'Create' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Client created');
  // Lands on the new client's page.
  await expect(page).toHaveURL(/\/clients\/c0000000-/);
  await expect(page.getByRole('heading', { level: 1, name: 'Blue Fern Studio (fictional)' })).toBeVisible();
  await expect(page.getByText('BFS')).toBeVisible();
  const posts = store.calls.filter((call) => call.method === 'POST' && call.url === '/api/v1/clients');
  expect(posts[posts.length - 1]?.body).toContain('"aliases":["Blue Fern","BFS"]');

  // Archive.
  await page.getByRole('button', { name: 'Archive' }).click();
  await page.getByRole('dialog', { name: /Archive Blue Fern/ }).getByRole('button', { name: 'Archive' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Client archived');
  await expect(page.getByRole('status').filter({ hasText: 'This client is archived' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Restore' })).toBeVisible();

  // Delete: a wrong name is refused, the right name deletes and returns to the list.
  await page.getByRole('button', { name: 'Delete' }).click();
  const confirm = page.getByRole('dialog', { name: 'Delete Blue Fern Studio (fictional)' });
  await expect(confirm.getByLabel('Client name')).toBeFocused();
  await confirm.getByLabel('Client name').fill('Blue Fern');
  await confirm.getByRole('button', { name: 'Delete' }).click();
  await expect(confirm.getByRole('alert')).toContainText('The name does not match.');
  await expectAccessible(page);
  await page.screenshot({ path: shot('client-delete', width, scheme) });
  await confirm.getByLabel('Client name').fill('Blue Fern Studio (fictional)');
  await confirm.getByRole('button', { name: 'Delete' }).click();
  await expect(page).toHaveURL(/\/clients$/);
  await expect(page.locator('.co-toast--success').last()).toContainText('Client deleted');
  const deleteCall = store.calls.find((call) => call.method === 'DELETE');
  expect(deleteCall?.url).toContain('confirm_name=Blue+Fern+Studio+%28fictional%29');
  expect(store.clients.some((item) => item.name === 'Blue Fern Studio (fictional)')).toBe(false);
  expect(errors()).toEqual([]);
});
}

test('clients: the technician has the same screens', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installFakeApi(page);
  await setView(page, 768, 'dark');
  await page.goto(`/clients/${HARBOURSIDE.id}`);
  await expect(page.getByRole('heading', { level: 1, name: HARBOURSIDE.name })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New job' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible();
  await expectAccessible(page);
});

test('clients: an unknown id shows the not-found state inside the shell', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await setView(page, 390, 'light');
  await page.goto('/clients/c1000000-0000-4000-8000-00000000ffff');
  await expect(page.getByRole('heading', { level: 1, name: 'Client not found' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'All clients' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('clients at 320 px: the table toolbar stacks and nothing crosses the viewport', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto('/clients');
  await expect(page.getByRole('table')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  // The stacked groups are as tall as their controls: no blank block between
  // the filters and the table (the row layout's flex-basis must not become a height).
  const start = page.locator('.co-table__toolbar-start');
  const startBox = await start.boundingBox();
  const filtersBox = await start.locator('> *').first().boundingBox();
  expect(startBox).not.toBeNull();
  expect(filtersBox).not.toBeNull();
  expect((startBox?.height ?? 0) - (filtersBox?.height ?? 0)).toBeLessThanOrEqual(1);
  const toolbarBox = await page.locator('.co-table__toolbar').boundingBox();
  expect(toolbarBox?.height ?? 0).toBeLessThan(260);
  await page.screenshot({ path: 'screenshots/clients-toolbar-320-light.png', fullPage: true });
  expect(errors()).toEqual([]);
});
