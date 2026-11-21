import { expect, test } from '@playwright/test';

import { installFakeApi, installIngestApi, installParserApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

async function installAll(page: Parameters<typeof installFakeApi>[0]) {
  const fake = await installFakeApi(page);
  const ingest = await installIngestApi(page);
  const parsers = await installParserApi(page, { fake, ingest });
  return { fake, ingest, parsers };
}

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`unmatched queue and split view at ${width} px, ${scheme}: the raw mail is text, the fields sit beside it, one click makes the job`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      const { fake, parsers } = await installAll(page);
      await setView(page, width, scheme);
      await page.goto('/unmatched');
      await expect(page.getByRole('heading', { level: 1, name: 'Unmatched' })).toBeVisible();
      await expect(page.getByText('4 unmatched results')).toBeVisible();
      const queue = page.getByRole('list', { name: 'Unmatched results' });
      await expect(queue.getByRole('button')).toHaveCount(4);
      // Newest first, the first one picked; the status is icon plus word.
      const first = queue.getByRole('button').first();
      await expect(first).toHaveAttribute('aria-current', 'true');
      await expect(first).toContainText('Nightly server backup');
      await expect(first.locator('.co-badge svg')).toHaveCount(1);
      await expect(queue.getByRole('button').last()).toContainText('Archive copy');
      // The raw mail on the left: literal text in JetBrains Mono, never HTML.
      const raw = page.getByTestId('unmatched-raw');
      await expect(raw).toBeVisible();
      await expect(raw).toContainText('<script>window.__pwned = 1</script>');
      await expect(raw).toContainText('<b>Bold</b> and <a href="https://example.test">a link</a> stay text.');
      expect(await raw.locator('script, b, a').count()).toBe(0);
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      expect(await raw.evaluate((element) => getComputedStyle(element).fontFamily)).toMatch(/JetBrains Mono/);
      // The fields on the right.
      const fields = page.locator('.co-split__pane--fields');
      await expect(fields.getByRole('heading', { level: 3, name: 'Extracted fields' })).toBeVisible();
      await expect(fields).toContainText('Harbourside Dental (fictional)');
      await expect(fields).toContainText('run-9001');
      await expect(fields).toContainText('vms');
      await expect(fields).toContainText('12');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('unmatched', width, scheme), fullPage: width > 390 });

      // Create job: everything prefilled from the mail; one click binds this
      // result and the two others with the same names.
      await page.getByRole('button', { name: 'Create job', exact: true }).click();
      const drawer = page.getByRole('dialog', { name: 'Create a job from this result' });
      await expect(drawer).toBeVisible();
      await expect(drawer.getByLabel('Client name')).toHaveValue('Harbourside Dental (fictional)');
      await expect(drawer.getByLabel('Name', { exact: true })).toHaveValue('Nightly server backup');
      await expect(drawer.getByLabel(/Match key/)).toHaveValue('Nightly server backup');
      await expectAccessible(page);
      await page.screenshot({ path: shot('unmatched-create', width, scheme) });
      await drawer.getByRole('button', { name: 'Create job' }).click();
      await expect(page.locator('.co-toast--success').last()).toContainText('Job created');
      const summary = drawer.getByRole('status');
      await expect(summary).toContainText('Bound to Nightly server backup for Harbourside Dental (fictional).');
      await expect(summary).toContainText('The job’s match key is now “Nightly server backup”.');
      await expect(summary).toContainText('The client already knows “Harbourside Dental (fictional)”.');
      await expect(summary).toContainText('2 other unmatched results with the same names were bound too.');
      const created = parsers.calls.find((call) => call.method === 'POST' && call.url.endsWith('/create-job'));
      expect(created?.body).toContain('"client_name":"Harbourside Dental (fictional)"');
      expect(created?.body).toContain('"match_key":"Nightly server backup"');
      expect(fake.jobs.some((item) => item.name === 'Nightly server backup' && item.match_key === 'Nightly server backup')).toBe(true);
      await drawer.getByRole('button', { name: 'Done' }).click();
      await expect(drawer).toBeHidden();
      // The three bound results left the queue; the next one is picked.
      await expect(page.getByText('1 unmatched result', { exact: true })).toBeVisible();
      await expect(queue.getByRole('button')).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 2, name: 'Archive copy' })).toBeVisible();
      await expect(page.getByText('This result came in through the API, without a mail.')).toBeVisible();
      await expectNoHorizontalOverflow(page);
      expect(errors()).toEqual([]);
    });
  }
}

for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
  test(`unmatched: assign to a job that has another key keeps it, offers Replace key and shows the old key (${width} px, ${scheme})`, async ({ page }) => {
    const errors = watchConsole(page);
    await stubApi(page, { me: ADMIN });
    const { fake, parsers } = await installAll(page);
    await setView(page, width, scheme);
    await page.goto('/unmatched');
    const queue = page.getByRole('list', { name: 'Unmatched results' });
    await queue.getByRole('button', { name: /Archive copy/ }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'Archive copy' })).toBeVisible();
    await page.getByRole('button', { name: 'Assign to a job' }).click();
    const dialog = page.getByRole('dialog', { name: 'Assign to a job' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('Find a job').fill('Cove');
    const cove = dialog.getByRole('radio', { name: /Cove server/ });
    await expect(cove).toBeVisible();
    await expect(dialog.getByRole('radio')).toHaveCount(1);
    // The row reads name over client with the key chip beside them (or under
    // them on a phone); the chip never sits left of the name or over the client.
    const nameBox = await cove.locator('.co-assign__job-name').boundingBox();
    const clientBox = await cove.locator('.co-assign__job-client').boundingBox();
    const keyBox = await cove.locator('.co-assign__job-key').boundingBox();
    const rowBox = await cove.boundingBox();
    expect(nameBox && clientBox && keyBox && rowBox).toBeTruthy();
    if (nameBox && clientBox && keyBox && rowBox) {
      expect(nameBox.x).toBeLessThanOrEqual(keyBox.x);
      expect(nameBox.y).toBeLessThanOrEqual(keyBox.y);
      expect(keyBox.x + keyBox.width).toBeLessThanOrEqual(rowBox.x + rowBox.width + 0.5);
      const overlaps = keyBox.x < clientBox.x + clientBox.width && clientBox.x < keyBox.x + keyBox.width && keyBox.y < clientBox.y + clientBox.height && clientBox.y < keyBox.y + keyBox.height;
      expect(overlaps).toBe(false);
    }
    await cove.click();
    // The job's key names another job name: keep or replace, keep by default.
    await expect(dialog.getByText('This job already has the key “Old tool name”. The mail names the job “Archive copy”.')).toBeVisible();
    await expect(dialog.getByRole('radio', { name: /Keep the job’s key/ })).toBeChecked();
    await expectAccessible(page);
    await page.screenshot({ path: shot('unmatched-assign', width, scheme) });
    await dialog.getByRole('button', { name: 'Assign', exact: true }).click();
    const summary = dialog.getByRole('status');
    await expect(summary).toContainText('Bound to Cove server for Northwind Legal (fictional).');
    await expect(summary).toContainText('The job keeps its current key “Old tool name”.');
    await expect(summary).toContainText('The client learned the alias “Blue Fern Studio (fictional)”.');
    const assign = parsers.calls.find((call) => call.method === 'POST' && call.url.endsWith('/assign'));
    expect(assign?.body).toContain('"replace_match_key":false');
    await expectAccessible(page);
    await page.screenshot({ path: shot('unmatched-bound', width, scheme) });
    // Replace key: the job takes the mail's job name and the old key is shown.
    await summary.getByRole('button', { name: 'Replace key' }).click();
    await expect(summary).toContainText('The old key “Old tool name” was replaced by “Archive copy”.');
    await expect(summary.getByRole('button', { name: 'Replace key' })).toHaveCount(0);
    expect(fake.jobs.find((item) => item.name === 'Cove server')?.match_key).toBe('Archive copy');
    const patch = fake.calls.find((call) => call.method === 'PATCH');
    expect(patch?.body).toContain('"match_key":"Archive copy"');
    await dialog.getByRole('button', { name: 'Done' }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText('3 unmatched results')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    expect(errors()).toEqual([]);
  });
}

test('unmatched: Replace chosen before the assign sends replace_match_key true and reads back the replaced key', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const { parsers } = await installAll(page);
  await setView(page, 768, 'light');
  await page.goto('/unmatched');
  await page.getByRole('list', { name: 'Unmatched results' }).getByRole('button', { name: /Archive copy/ }).click();
  await page.getByRole('button', { name: 'Assign to a job' }).click();
  const dialog = page.getByRole('dialog', { name: 'Assign to a job' });
  await dialog.getByRole('radio', { name: /Cove server/ }).click();
  await dialog.getByRole('radio', { name: /Replace the key with “Archive copy”/ }).check();
  await dialog.getByRole('button', { name: 'Assign', exact: true }).click();
  const summary = dialog.getByRole('status');
  await expect(summary).toContainText('The old key “Old tool name” was replaced by “Archive copy”.');
  await expect(summary.getByRole('button', { name: 'Replace key' })).toHaveCount(0);
  const assign = parsers.calls.find((call) => call.method === 'POST' && call.url.endsWith('/assign'));
  expect(assign?.body).toContain('"replace_match_key":true');
});

test('unmatched: a suggestion fills the schedule editor; too few runs offers daily 02:00 with the reason', async ({ page }) => {
  // The 422 of a suggestion below three runs is expected.
  const errors = watchConsole(page, [422]);
  await stubApi(page, { me: ADMIN });
  await installAll(page);
  await setView(page, 768, 'dark');
  await page.goto('/unmatched');
  await expect(page.getByRole('heading', { level: 2, name: 'Nightly server backup' })).toBeVisible();
  // Three runs with these names: the median time.
  await page.getByRole('button', { name: 'Suggest schedule' }).click();
  const drawer = page.getByRole('dialog', { name: 'Create a job from this result' });
  await expect(drawer.getByText(/Daily at 02:15 \(.+\), the median finished time of 3 runs/)).toBeVisible();
  await expect(drawer.getByLabel('Time 1')).toHaveValue('02:15');
  await expectAccessible(page);
  await page.screenshot({ path: shot('unmatched-suggest', 768, 'dark'), fullPage: true });
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();
  // One run: the default, said as such, still editable.
  await page.getByRole('list', { name: 'Unmatched results' }).getByRole('button', { name: /Archive copy/ }).click();
  await page.getByRole('button', { name: 'Suggest schedule' }).click();
  await expect(drawer.getByText(/Too few runs to suggest a time: Only 1 run with these names; 3 are needed\. Daily at 02:00/)).toBeVisible();
  await expect(drawer.getByLabel('Time 1')).toHaveValue('02:00');
  await drawer.getByLabel('Time 1').fill('03:30');
  await expect(drawer.getByLabel('Time 1')).toHaveValue('03:30');
  await expectAccessible(page);
  await page.screenshot({ path: shot('unmatched-suggest-default', 768, 'dark'), fullPage: true });
  expect(errors()).toEqual([]);
});

test('unmatched: loading, empty and error states are designed', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const fake = await installFakeApi(page);
  const ingest = await installIngestApi(page);
  await installParserApi(page, { fake, ingest }, { results: [] });
  await setView(page, 1440, 'light');
  await page.goto('/unmatched');
  // Both panes say it: the queue and the detail.
  await expect(page.getByText('Nothing is waiting').first()).toBeVisible();
  await expect(page.getByText('Every result found its job. New results that no job claims appear here.').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Messages no pack could read' })).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/unmatched-empty-1440-light.png' });

  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/unmatched?**', async (route) => {
    await gate;
    await route.fulfill({ status: 500, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-e2e-500' }) });
  });
  await page.reload();
  await expect(page.locator('.co-queue--loading')).toBeVisible();
  await page.screenshot({ path: 'screenshots/unmatched-loading-1440-light.png' });
  release();
  await expect(page.getByRole('alert')).toContainText('req-e2e-500');
  await expect(page.getByRole('alert').getByRole('button', { name: 'Try again' })).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/unmatched-error-1440-light.png' });
});

test('unmatched: the technician has the same screen and actions', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installAll(page);
  await setView(page, 390, 'light');
  await page.goto('/unmatched');
  await expect(page.getByRole('heading', { level: 1, name: 'Unmatched' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create job', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Assign to a job' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Suggest schedule' })).toBeVisible();
  await expect(page.getByTestId('unmatched-raw')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
