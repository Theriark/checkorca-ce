import { expect, test } from '@playwright/test';

import { NORTHWIND, SEED_MESSAGES, SMTP_INBOX, installFakeApi, installIngestApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

const EML = ['From: Veeam Backup <veeam@backup.example.test>', `To: ${SMTP_INBOX.address}`, 'Subject: [Warning] Nightly server backup - Harbourside Dental (fictional)', 'Date: Fri, 20 Nov 2026 01:05:00 +0000', 'Message-ID: <upload-e2e-0001@backup.example.test>', 'Content-Type: text/plain; charset=utf-8', '', 'Backup job: Nightly server backup', 'Status: Warning', '1 of 1 VMs processed, 1 warning.', ''].join('\r\n');

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`messages list and message detail at ${width} px, ${scheme}: HTML in the body is literal text`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await installFakeApi(page);
      await installIngestApi(page);
      await setView(page, width, scheme);
      await page.goto('/messages');
      await expect(page.getByRole('heading', { level: 1, name: 'Messages' })).toBeVisible();
      const table = page.getByRole('table', { name: 'Messages with their sender, inbox, parse state and client' });
      await expect(table.locator('tbody tr')).toHaveCount(4);
      await expect(page.getByText('4 messages')).toBeVisible();
      // Newest first; the inbox is kind plus label; the state is icon plus word.
      await expect(table.locator('tbody tr').first()).toContainText('Alerts mailbox');
      const parsed = table.locator('tbody tr').filter({ hasText: 'Synology Active Backup' });
      await expect(parsed).toContainText('Parsed');
      await expect(parsed.locator('.co-badge svg')).toHaveCount(1);
      await expect(parsed.getByRole('link', { name: NORTHWIND.name })).toBeVisible();
      // The Veeam mail stored in two inboxes carries the duplicate flag on both rows.
      await expect(table.getByText('Duplicate')).toHaveCount(2);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('messages', width, scheme), fullPage: width > 390 });

      await table.getByRole('link', { name: SEED_MESSAGES[0]?.subject ?? '' }).first().click();
      await expect(page.getByRole('heading', { level: 1, name: SEED_MESSAGES[0]?.subject ?? '' })).toBeVisible();
      const body = page.getByTestId('message-body');
      await expect(body).toBeVisible();
      // The script tag is text, not an element, and never ran.
      await expect(body).toContainText('<script>window.__pwned = 1</script>');
      await expect(body).toContainText('<b>Bold</b> and <a href="https://example.test">a link</a> stay text.');
      expect(await body.locator('script, b, a').count()).toBe(0);
      expect(await page.locator('iframe').count()).toBe(0);
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      expect(await body.evaluate((element) => getComputedStyle(element).fontFamily)).toMatch(/JetBrains Mono/);
      // A long body scrolls inside its box rather than stretching the page.
      const box = body.locator('..');
      expect(await box.evaluate((element) => element.scrollHeight > element.clientHeight && getComputedStyle(element).overflowY === 'auto')).toBe(true);
      await expect(page.getByRole('heading', { level: 2, name: 'Headers' })).toBeVisible();
      await expect(page.getByText('text/html; charset="utf-8"')).toBeVisible();
      await expect(page.getByText('18.0 KB')).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('message-detail', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

test('messages: loading, empty and error states are designed; the inbox filter asks the server', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installIngestApi(page, { messages: [] });
  await setView(page, 1440, 'light');
  await page.goto('/messages');
  await expect(page.getByRole('heading', { level: 3, name: 'No messages yet' })).toBeVisible();
  await expect(page.locator('.co-empty').getByRole('button', { name: 'Upload .eml' })).toBeVisible();
  await page.screenshot({ path: 'screenshots/messages-empty-1440-light.png' });

  await page.route('**/api/v1/messages?**', (route) =>
    route.fulfill({ status: 500, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-e2e-500' }) }),
  );
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('req-e2e-500');
  await page.unroute('**/api/v1/messages?**');
  await page.reload();
  await page.getByRole('combobox', { name: 'Inbox' }).click();
  await page.getByRole('option', { name: 'Veeam reports' }).click();
  await expect.poll(() => store.calls.some((call) => call.url.includes(`inbox_id=${SMTP_INBOX.id}`))).toBe(true);
  await page.getByRole('combobox', { name: 'Parse state' }).click();
  await page.getByRole('option', { name: 'Error' }).click();
  await expect.poll(() => store.calls.some((call) => call.url.includes('parse_state=error'))).toBe(true);
});

test('messages: the results the parser read are listed on the detail', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await installIngestApi(page);
  await setView(page, 768, 'dark');
  await page.goto(`/messages/${SEED_MESSAGES[1]?.id ?? ''}`);
  const results = page.getByRole('table', { name: 'Results' });
  await expect(results.locator('tbody tr')).toHaveCount(1);
  await expect(results).toContainText('Warning');
  await expect(results).toContainText('Synology ABB');
  await expect(results).toContainText('run-4411');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/message-results-768-dark.png', fullPage: true });
});

test('messages: an unknown id shows the not-found state inside the shell', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  await installIngestApi(page);
  await setView(page, 390, 'light');
  await page.goto('/messages/m1000000-0000-4000-8000-00000000ffff');
  await expect(page.getByRole('heading', { level: 1, name: 'Message not found' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'All messages' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

// The upload dialog runs on a desktop in light and on a phone in dark.
for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
test(`messages: .eml upload refuses an oversize file and a non-mail file, stores a report, and says when it is a duplicate (${width} px, ${scheme})`, async ({ page }) => {
  // The non-mail file is refused with 422 on purpose.
  const errors = watchConsole(page, [422]);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installIngestApi(page);
  await setView(page, width, scheme);
  await page.goto('/messages');
  await page.getByRole('button', { name: 'Upload .eml' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Upload an .eml file' });
  await dialog.getByRole('button', { name: 'Upload' }).click();
  await expect(dialog.getByText('Choose an inbox.')).toBeVisible();
  await expect(dialog.getByText('Choose an .eml file first.')).toBeVisible();
  await dialog.getByRole('combobox', { name: 'Inbox' }).click();
  await page.getByRole('option', { name: /Veeam reports/ }).click();
  // Over 5 MiB: refused before anything is sent.
  await dialog.getByLabel('.eml file').setInputFiles({ name: 'huge.eml', mimeType: 'message/rfc822', buffer: Buffer.alloc(5 * 1024 * 1024 + 1, 0x41) });
  await expect(dialog.getByText('The file is 5.0 MB; the limit is 5 MB.')).toBeVisible();
  await dialog.getByRole('button', { name: 'Upload' }).click();
  expect(store.calls.filter((call) => call.url === '/api/v1/messages/upload')).toHaveLength(0);
  // Not a mail: the server's sentence.
  await dialog.getByLabel('.eml file').setInputFiles({ name: 'notes.eml', mimeType: 'message/rfc822', buffer: Buffer.from('just some notes, no headers') });
  await dialog.getByRole('button', { name: 'Upload' }).click();
  await expect(dialog.getByRole('alert')).toContainText('The file was not stored');
  await expect(dialog.getByRole('alert')).toContainText('Send one RFC 822 message: headers, a blank line, then the body.');
  await expectAccessible(page);
  await page.screenshot({ path: shot('message-upload', width, scheme) });
  // A synthetic Veeam-style report is stored and opened.
  await dialog.getByLabel('.eml file').setInputFiles({ name: 'veeam-warning.eml', mimeType: 'message/rfc822', buffer: Buffer.from(EML) });
  await dialog.getByRole('button', { name: 'Upload' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Message stored');
  await expect(page).toHaveURL(/\/messages\/m0000000-/);
  await expect(page.getByRole('heading', { level: 1, name: '[Warning] Nightly server backup - Harbourside Dental (fictional)' })).toBeVisible();
  await expect(page.getByTestId('message-body')).toContainText('1 of 1 VMs processed, 1 warning.');
  const upload = store.calls.find((call) => call.url === '/api/v1/messages/upload' && call.body?.includes('upload-e2e-0001'));
  expect(upload?.body).toContain(`name="inbox_id"`);
  // The same Message-ID a second time: one row, said as a duplicate.
  await page.goto('/messages');
  const rows = page.getByRole('table').locator('tbody tr');
  await expect(rows).toHaveCount(5);
  await page.getByRole('button', { name: 'Upload .eml' }).first().click();
  const again = page.getByRole('dialog', { name: 'Upload an .eml file' });
  await again.getByRole('combobox', { name: 'Inbox' }).click();
  await page.getByRole('option', { name: /Veeam reports/ }).click();
  await again.getByLabel('.eml file').setInputFiles({ name: 'veeam-warning.eml', mimeType: 'message/rfc822', buffer: Buffer.from(EML) });
  await again.getByRole('button', { name: 'Upload' }).click();
  await expect(again.getByRole('status').filter({ hasText: 'Already stored' })).toBeVisible();
  await expectAccessible(page);
  await again.getByRole('button', { name: 'Open the message' }).click();
  await expect(page).toHaveURL(/\/messages\/m0000000-/);
  await page.goto('/messages');
  await expect(rows).toHaveCount(5);
  expect(errors()).toEqual([]);
});
}

test('messages: the technician has the same screens', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installFakeApi(page);
  await installIngestApi(page);
  await setView(page, 390, 'light');
  await page.goto('/messages');
  await expect(page.getByRole('heading', { level: 1, name: 'Messages' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Upload .eml' })).toBeVisible();
  await page.getByRole('table').locator('tbody tr').first().click();
  await expect(page.getByTestId('message-body')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
