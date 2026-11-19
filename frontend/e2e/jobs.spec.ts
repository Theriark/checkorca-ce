import { expect, test } from '@playwright/test';

import { HARBOURSIDE, installFakeApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

const CSV = ['client,job,kind,schedule_kind,schedule_expr,timezone', 'Blue Fern Studio (fictional),Acronis cloud,backup,daily,23:00,Europe/Lisbon', 'Blue Fern Studio (fictional),Files sync,backup,daily,not-a-time,Europe/Lisbon', 'Blue Fern Studio (fictional),DB dump,script,cron,30 1 * * *,Europe/Lisbon'].join('\r\n');

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`jobs list, drawer with preview and import dialog at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await installFakeApi(page);
      await setView(page, width, scheme);
      await page.goto('/jobs');
      await expect(page.getByRole('heading', { level: 1, name: 'Jobs' })).toBeVisible();
      const table = page.getByRole('table', { name: 'Jobs with their schedule and state' });
      await expect(table.locator('tbody tr')).toHaveCount(4);
      await expect(page.getByText('4 jobs')).toBeVisible();
      // Status is icon plus word: the paused job carries both.
      const paused = table.locator('tbody tr').filter({ hasText: 'Cove server' });
      await expect(paused.locator('.co-badge svg')).toHaveCount(1);
      await expect(paused).toContainText('Paused');
      await expect(paused).toContainText('until resumed');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('jobs', width, scheme), fullPage: true });

      // The drawer with a daily 23:00 schedule: five times from the preview.
      await page.getByRole('button', { name: 'New job' }).first().click();
      const drawer = page.getByRole('dialog', { name: 'New job' });
      await expect(drawer).toBeVisible();
      await drawer.getByLabel('Time zone').fill('Europe/Lisbon');
      await expect(drawer.locator('.co-preview__item')).toHaveCount(5);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await drawer.locator('.co-preview').scrollIntoViewIfNeeded();
      await page.screenshot({ path: shot('job-drawer', width, scheme) });
      await page.keyboard.press('Escape');
      await expect(drawer).toBeHidden();

      // The import dialog after a dry run with one bad row.
      await page.getByRole('button', { name: 'Import CSV' }).click();
      const dialog = page.getByRole('dialog', { name: 'Import jobs from CSV' });
      await dialog.getByLabel('CSV file').setInputFiles({ name: 'jobs.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) });
      await dialog.getByRole('button', { name: 'Check the file' }).click();
      await expect(dialog.getByRole('table', { name: 'Rows with errors' })).toBeVisible();
      await expect(dialog.getByRole('table', { name: 'Rows with errors' }).locator('tbody tr')).toHaveCount(1);
      await expect(dialog.getByRole('table', { name: 'Rows with errors' })).toContainText('3');
      await expect(dialog.getByRole('button', { name: 'Import 2 rows' })).toBeEnabled();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('job-import', width, scheme) });
      expect(errors()).toEqual([]);
    });
  }
}

test('jobs: filters by client, kind and state, and the archived toggle', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const store = await installFakeApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/jobs');
  const rows = page.getByRole('table').locator('tbody tr');
  await expect(rows).toHaveCount(4);
  await page.getByRole('combobox', { name: 'Client' }).click();
  await page.getByRole('option', { name: HARBOURSIDE.name }).click();
  await expect(rows).toHaveCount(2);
  await page.getByRole('combobox', { name: 'Kind' }).click();
  await page.getByRole('option', { name: 'Script' }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('SQL dump script');
  await page.getByRole('combobox', { name: 'Kind' }).click();
  await page.getByRole('option', { name: 'Any kind' }).click();
  await page.getByRole('combobox', { name: 'Client' }).click();
  await page.getByRole('option', { name: 'Any client' }).click();
  await page.getByRole('combobox', { name: 'State' }).click();
  await page.getByRole('option', { name: 'Paused' }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText('Cove server');
  await expect(rows.last()).toContainText('until Tue, 5 Jan 2027, 09:30');
  await page.getByRole('combobox', { name: 'State' }).click();
  await page.getByRole('option', { name: 'Any state' }).click();
  await page.getByRole('searchbox', { name: 'Search jobs' }).fill('veeam');
  await expect(rows).toHaveCount(1);
  await page.getByRole('searchbox', { name: 'Search jobs' }).fill('');
  await page.getByRole('switch', { name: 'Show archived' }).check();
  await expect(page.getByRole('heading', { level: 3, name: 'No archived jobs' })).toBeVisible();
  expect(store.calls.some((call) => call.url.includes('archived=true'))).toBe(true);
});

test('jobs: create a daily 23:00 Europe/Lisbon job, pause, resume and archive it', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const store = await installFakeApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/jobs');
  await page.getByRole('button', { name: 'New job' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New job' });
  // Required fields are asked for before anything is sent.
  await drawer.getByRole('button', { name: 'Create job' }).click();
  await expect(drawer.getByText('Choose a client.')).toBeVisible();
  await expect(drawer.getByText('Enter a name.')).toBeVisible();
  await drawer.getByRole('combobox', { name: 'Client' }).click();
  await page.getByRole('option', { name: HARBOURSIDE.name }).click();
  await drawer.getByLabel('Name').fill('Acronis cloud');
  await expect(drawer.getByRole('group', { name: 'Schedule kind' }).getByRole('button', { name: 'Daily', pressed: true })).toBeVisible();
  await expect(drawer.getByLabel('Time 1')).toHaveValue('23:00');
  await drawer.getByLabel('Time zone').fill('Europe/Lisbon');
  await expect(drawer.locator('.co-preview__item')).toHaveCount(5);
  await expect(drawer.locator('.co-preview__item').first()).toContainText('23:00');
  await drawer.getByRole('button', { name: 'Create job' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Job created');
  await expect(drawer).toBeHidden();
  const created = store.calls.find((call) => call.method === 'POST' && call.url === '/api/v1/jobs');
  expect(created?.body).toContain('"schedule_kind":"daily"');
  expect(created?.body).toContain('"schedule_expr":"23:00"');
  expect(created?.body).toContain('"timezone":"Europe/Lisbon"');
  const row = page.getByRole('table').locator('tbody tr').filter({ hasText: 'Acronis cloud' });
  await expect(row).toBeVisible();
  await expect(row).toContainText('No result yet');
  await expect(row).toContainText('Not yet');

  // Pause with a time, then resume.
  await row.getByRole('button', { name: 'Actions for Acronis cloud' }).click();
  await page.getByRole('menuitem', { name: 'Pause' }).click();
  const pause = page.getByRole('dialog', { name: 'Pause Acronis cloud' });
  await expect(pause.getByLabel(/Until/)).toBeFocused();
  await pause.getByLabel(/Until/).fill('2027-01-05T09:30');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/job-pause-1440-light.png' });
  await pause.getByRole('button', { name: 'Pause' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Job paused');
  await expect(row).toContainText('Paused');
  await expect(row).toContainText('until');
  const pauseCall = store.calls.find((call) => call.method === 'POST' && call.url.endsWith('/pause'));
  expect(pauseCall?.body).toContain('"until":"2027-01-05T');
  await row.getByRole('button', { name: 'Actions for Acronis cloud' }).click();
  await page.getByRole('menuitem', { name: 'Resume' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Job resumed');
  await expect(row).toContainText('No result yet');

  // Edit shows the ping URL with a copy button.
  await row.click();
  const edit = page.getByRole('dialog', { name: 'Edit job' });
  await expect(edit.getByLabel('Ping URL')).toHaveValue(/\/api\/v1\/ping\//);
  await expect(edit.getByRole('button', { name: 'Copy' })).toBeVisible();
  await expect(edit.locator('.co-preview__item')).toHaveCount(5);
  await page.keyboard.press('Escape');

  // Archive.
  await row.getByRole('button', { name: 'Actions for Acronis cloud' }).click();
  await page.getByRole('menuitem', { name: 'Archive' }).click();
  await page.getByRole('dialog', { name: 'Archive Acronis cloud' }).getByRole('button', { name: 'Archive' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Job archived');
  await expect(row).toHaveCount(0);
  await page.getByRole('switch', { name: 'Show archived' }).check();
  await expect(page.getByRole('table').locator('tbody tr').filter({ hasText: 'Acronis cloud' })).toContainText('Archived');
  expect(errors()).toEqual([]);
});

test('jobs: the preview shows the server error text for an unusable schedule, debounced', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const store = await installFakeApi(page);
  await setView(page, 768, 'light');
  await page.goto('/jobs');
  await page.getByRole('button', { name: 'New job' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New job' });
  await drawer.getByRole('group', { name: 'Schedule kind' }).getByRole('button', { name: 'Cron' }).click();
  await drawer.getByLabel('Time zone').fill('Europe/Lisbon');
  await drawer.getByLabel('Expression').pressSequentially('0 23 * *', { delay: 20 });
  // The message sits under the field and in the preview panel.
  await expect(drawer.locator('.co-field__error')).toContainText('A cron expression has five fields');
  await expect(drawer.getByRole('status').filter({ hasText: 'The schedule cannot be used' })).toContainText('A cron expression has five fields');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/job-preview-error-768-light.png' });
  await drawer.getByLabel('Expression').pressSequentially(' 1-5', { delay: 20 });
  await expect(drawer.locator('.co-preview__item')).toHaveCount(5);
  // Typing twelve characters asked the server a handful of times, not twelve.
  const previews = store.calls.filter((call) => call.url === '/api/v1/schedule/preview');
  expect(previews.length).toBeLessThan(12);
  // A time zone the server does not know is reported on the zone field.
  await drawer.getByLabel('Time zone').fill('Mars');
  await expect(drawer.locator('.co-field__error')).toContainText('Unknown time zone: Mars.');
});

test('jobs: import with one bad row checks first, then imports the rest', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const store = await installFakeApi(page);
  await setView(page, 390, 'dark');
  await page.goto('/jobs');
  await page.getByRole('button', { name: 'Import CSV' }).click();
  const dialog = page.getByRole('dialog', { name: 'Import jobs from CSV' });
  await dialog.getByRole('button', { name: 'Check the file' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Choose a CSV file first.');
  await dialog.getByLabel('CSV file').setInputFiles({ name: 'jobs.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) });
  await dialog.getByRole('button', { name: 'Check the file' }).click();
  await expect(dialog.getByText('Jobs to create')).toBeVisible();
  await expect(dialog.getByRole('table', { name: 'Rows with errors' })).toContainText('schedule_expr');
  await expectNoHorizontalOverflow(page);
  const dryRun = store.calls.find((call) => call.url.includes('import.csv'));
  expect(dryRun?.url).toContain('dry_run=true');
  await dialog.getByRole('button', { name: 'Import 2 rows' }).click();
  await expect(dialog.getByRole('status').filter({ hasText: 'Import finished' })).toBeVisible();
  await expect(page.locator('.co-toast--success')).toContainText('2 created, 0 updated, 1 clients created');
  const real = store.calls.filter((call) => call.url.includes('import.csv'))[1];
  expect(real?.url).toContain('dry_run=false');
  await dialog.getByRole('button', { name: 'Close' }).first().click();
  await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(6);
  expect(errors()).toEqual([]);
});

test('jobs: export downloads jobs.csv', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/jobs');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  expect((await download).suggestedFilename()).toBe('jobs.csv');
  await expect(page.locator('.co-toast--success')).toContainText('Export downloaded');
});

test('jobs: the technician can create, pause and archive too', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installFakeApi(page);
  await setView(page, 390, 'light');
  await page.goto('/jobs');
  await expect(page.getByRole('button', { name: 'New job' }).first()).toBeVisible();
  const row = page.getByRole('table').locator('tbody tr').filter({ hasText: 'Veeam nightly' });
  await row.getByRole('button', { name: 'Actions for Veeam nightly' }).click();
  await expect(page.getByRole('menuitem', { name: 'Pause' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Archive' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expectNoHorizontalOverflow(page);
});
