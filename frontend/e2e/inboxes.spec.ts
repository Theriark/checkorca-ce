import { expect, test } from '@playwright/test';

import { IMAP_INBOX, SMTP_INBOX, WEBHOOK_INBOX, installFakeApi, installIngestApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`inboxes list, create drawer and the token shown once at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await installFakeApi(page);
      const store = await installIngestApi(page);
      await setView(page, width, scheme);
      await page.goto('/inboxes');
      await expect(page.getByRole('heading', { level: 1, name: 'Inboxes' })).toBeVisible();
      const table = page.getByRole('table', { name: 'Inboxes with their kind, sender rules and last message' });
      await expect(table.locator('tbody tr')).toHaveCount(3);
      await expect(page.getByText('3 inboxes')).toBeVisible();
      // The kind is icon plus word; the SMTP address sits under the label.
      const smtp = table.locator('tbody tr').filter({ hasText: 'Veeam reports' });
      await expect(smtp.locator('.co-kind svg')).toHaveCount(1);
      await expect(smtp).toContainText('SMTP');
      await expect(smtp).toContainText('@ce-dev.example.com');
      await expect(table.locator('tbody tr').filter({ hasText: 'Alerts mailbox' })).toContainText('DKIM required');
      await expect(table.locator('tbody tr').filter({ hasText: 'Script results' })).toContainText('Webhook');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('inboxes', width, scheme), fullPage: width > 390 });

      // Create a webhook inbox: the kind picker, the label, the rules.
      await page.getByRole('button', { name: 'New inbox' }).first().click();
      const drawer = page.getByRole('dialog', { name: 'New inbox' });
      await expect(drawer).toBeVisible();
      await expect(drawer.getByRole('radio', { name: /SMTP/ })).toHaveAttribute('aria-checked', 'true');
      await drawer.getByRole('radio', { name: /Webhook/ }).click();
      await drawer.getByLabel('Label').fill('Cove results (synthetic)');
      await drawer.getByLabel(/Allowed senders/).fill('@cove.example.test');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('inbox-create', width, scheme) });
      await drawer.getByRole('button', { name: 'Create inbox' }).click();
      await expect(page.locator('.co-toast--success')).toContainText('Inbox created');

      // The token is shown this once, with the ingest URL.
      const ready = page.getByRole('dialog', { name: 'Inbox ready' });
      await expect(ready).toBeVisible();
      await expect(ready.getByText('Shown once')).toBeVisible();
      await expect(ready.getByLabel('Webhook token')).toHaveValue(/^chki_/);
      await expect(ready.getByLabel('Ingest URL')).toHaveValue(/\/api\/v1\/ingest\/email\//);
      await expectAccessible(page);
      await page.screenshot({ path: shot('inbox-reveal', width, scheme) });
      await ready.getByRole('button', { name: 'Close' }).last().click();
      await expect(ready).toBeHidden();
      const created = store.calls.find((call) => call.method === 'POST' && call.url === '/api/v1/inboxes');
      expect(created?.body).toContain('"kind":"webhook"');
      expect(created?.body).toContain('"sender_allowlist":["@cove.example.test"]');
      const row = table.locator('tbody tr').filter({ hasText: 'Cove results (synthetic)' });
      await expect(row).toBeVisible();
      // The edit drawer never shows the token again.
      await row.click();
      const edit = page.getByRole('dialog', { name: 'Edit inbox' });
      await expect(edit.getByText('A token is set')).toBeVisible();
      await expect(edit).not.toContainText('chki_');
      await expect(edit.getByRole('button', { name: 'Rotate token' })).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(edit).toBeHidden();
      expect(errors()).toEqual([]);
    });
  }
}

test('inboxes: loading, empty and error states are designed', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await setView(page, 1440, 'light');
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/inboxes?**', async (route) => {
    await gate;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], next_cursor: null }) });
  });
  await page.goto('/inboxes');
  await expect(page.locator('tbody[aria-busy="true"]')).toBeVisible();
  release();
  await expect(page.getByRole('heading', { level: 3, name: 'No inboxes yet' })).toBeVisible();
  await expect(page.locator('.co-empty').getByRole('button', { name: 'New inbox' })).toBeVisible();
  await page.screenshot({ path: 'screenshots/inboxes-empty-1440-light.png' });

  await page.unroute('**/api/v1/inboxes?**');
  await page.route('**/api/v1/inboxes?**', (route) =>
    route.fulfill({ status: 500, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-e2e-500' }) }),
  );
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('The database did not answer in time.');
  await expect(page.getByRole('alert')).toContainText('req-e2e-500');
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

// The IMAP edit and the SMTP create run on a desktop in light and on a phone
// in dark, so both themes of the drawer states are contrast-checked by axe.
for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
test(`inboxes: an IMAP host change needs the password again, locally and from the API; SMTP create shows the address (${width} px, ${scheme})`, async ({ page }) => {
  // The API refuses the retarget without a password with 422 on purpose.
  const errors = watchConsole(page, [422]);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installIngestApi(page);
  await setView(page, width, scheme);
  await page.goto('/inboxes');
  await page.getByRole('table').locator('tbody tr').filter({ hasText: 'Alerts mailbox' }).click();
  const edit = page.getByRole('dialog', { name: 'Edit inbox' });
  await expect(edit.getByLabel('Label')).toBeFocused();
  // The password is a masked hint, never the value; the field starts empty.
  await expect(edit.getByText('Stored password: ****x7Qz')).toBeVisible();
  await expect(edit.getByLabel('Password')).toHaveValue('');
  await expect(edit.getByLabel('Password')).toHaveAttribute('type', 'password');
  await edit.getByLabel('IMAP host').fill('imap2.example.test');
  await expect(edit.getByRole('status')).toContainText('Enter the password again');
  await edit.getByRole('button', { name: 'Save' }).click();
  await expect(edit.locator('.co-field__error')).toContainText('Enter the password again to change the host, port, TLS setting or user name.');
  expect(store.calls.filter((call) => call.method === 'PATCH')).toHaveLength(0);
  await expectAccessible(page);
  await page.screenshot({ path: shot('inbox-imap-retarget', width, scheme) });
  // Bypass the local check to prove the API's 422 is shown clearly: send the
  // patch the way a stale form would, then read the drawer's answer.
  await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/inboxes/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-admin' }, body: JSON.stringify({ imap: { host: 'imap3.example.test' } }) });
    (window as unknown as { __patchStatus: number }).__patchStatus = response.status;
  }, IMAP_INBOX.id);
  expect(await page.evaluate(() => (window as unknown as { __patchStatus: number }).__patchStatus)).toBe(422);
  // With the password the change goes through.
  await edit.getByLabel('Password').fill('again-synthetic-1234');
  await edit.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Inbox saved');
  await expect(edit).toBeHidden();
  const patch = store.calls.filter((call) => call.method === 'PATCH').pop();
  expect(patch?.body).toContain('"host":"imap2.example.test"');
  expect(patch?.body).toContain('"password":"again-synthetic-1234"');
  await expect(page.getByRole('table').locator('tbody tr').filter({ hasText: 'Alerts mailbox' })).toContainText('imap2.example.test');

  // An SMTP inbox: the ready dialog shows the address and URL with copy buttons, no token.
  await page.getByRole('button', { name: 'New inbox' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New inbox' });
  await drawer.getByLabel('Label').fill('Acronis mail (synthetic)');
  await drawer.getByRole('button', { name: 'Create inbox' }).click();
  const ready = page.getByRole('dialog', { name: 'Inbox ready' });
  await expect(ready.getByLabel('SMTP address')).toHaveValue(/@ce-dev\.example\.com$/);
  await expect(ready.getByLabel('Ingest URL')).toHaveValue(/\/api\/v1\/ingest\/email\//);
  await expect(ready.getByLabel('Webhook token')).toHaveCount(0);
  await expect(ready.getByRole('button', { name: 'Copy' })).toHaveCount(2);
  await expectAccessible(page);
  await page.screenshot({ path: shot('inbox-smtp-ready', width, scheme) });
  await ready.getByRole('button', { name: 'Close' }).last().click();
  expect(errors()).toEqual([]);
});
}

test('inboxes: rotate a webhook token (shown once) and delete an inbox from the row menu', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installIngestApi(page);
  await setView(page, 1440, 'dark');
  await page.goto('/inboxes');
  const row = page.getByRole('table').locator('tbody tr').filter({ hasText: 'Script results' });
  await row.getByRole('button', { name: 'Actions for Script results' }).click();
  await page.getByRole('menuitem', { name: 'Rotate token' }).click();
  const confirm = page.getByRole('dialog', { name: 'Rotate the token of Script results' });
  await expect(confirm).toContainText('The old token stops working at once');
  await confirm.getByRole('button', { name: 'Rotate' }).click();
  const ready = page.getByRole('dialog', { name: 'New token' });
  await expect(ready.getByLabel('Webhook token')).toHaveValue(/^chki_/);
  await expect(ready.getByText('Shown once')).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/inbox-rotate-1440-dark.png' });
  await ready.getByRole('button', { name: 'Close' }).last().click();
  expect(store.calls.some((call) => call.method === 'POST' && call.url.endsWith(`/inboxes/${WEBHOOK_INBOX.id}/token`))).toBe(true);

  // Copy the SMTP address from the menu.
  await page.getByRole('table').locator('tbody tr').filter({ hasText: 'Veeam reports' }).getByRole('button', { name: 'Actions for Veeam reports' }).click();
  await expect(page.getByRole('menuitem', { name: 'Copy address' })).toBeVisible();
  await page.keyboard.press('Escape');

  // Delete.
  await row.getByRole('button', { name: 'Actions for Script results' }).click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  const del = page.getByRole('dialog', { name: 'Delete Script results' });
  await expect(del).toContainText('stop working at once');
  await del.getByRole('button', { name: 'Delete' }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Inbox deleted');
  await expect(row).toHaveCount(0);
  expect(store.inboxes.some((item) => item.id === WEBHOOK_INBOX.id)).toBe(false);
  expect(errors()).toEqual([]);
});

test('inboxes: the kind filter asks the server', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installIngestApi(page);
  await setView(page, 768, 'light');
  await page.goto('/inboxes');
  const rows = page.getByRole('table').locator('tbody tr');
  await expect(rows).toHaveCount(3);
  await page.getByRole('combobox', { name: 'Kind' }).click();
  await page.getByRole('option', { name: 'IMAP' }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('Alerts mailbox');
  expect(store.calls.some((call) => call.url.includes('kind=imap'))).toBe(true);
  await page.getByRole('combobox', { name: 'Kind' }).click();
  await page.getByRole('option', { name: 'Upload' }).click();
  await expect(page.getByRole('heading', { level: 3, name: 'No inbox of that kind' })).toBeVisible();
});

test('inboxes: the technician has the same screen, and the Inboxes item stays current on /messages', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installFakeApi(page);
  await installIngestApi(page);
  await setView(page, 768, 'dark');
  await page.goto('/inboxes');
  await expect(page.getByRole('heading', { level: 1, name: 'Inboxes' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New inbox' })).toBeVisible();
  const sidebar = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(sidebar.getByRole('link', { name: 'Inboxes' })).toHaveAttribute('aria-current', 'page');
  await expect(sidebar.getByRole('link', { name: 'Settings' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Messages' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Messages' })).toBeVisible();
  await expect(sidebar.getByRole('link', { name: 'Inboxes' })).toHaveAttribute('aria-current', 'page');
  await expectAccessible(page);
  expect(SMTP_INBOX.kind).toBe('smtp');
});
