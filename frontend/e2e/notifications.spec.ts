import { expect, test } from '@playwright/test';

import type { NotificationOut } from '../src/api/notifications';
import { installFakeApi, installNotificationsApi } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNothingRan, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

/** The flows that provoke a problem answer on purpose. */
const EXPECTED = [422];

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`notifications: the three tabs and the digest settings at ${width} px, ${scheme}`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      await installNotificationsApi(page);
      await setView(page, width, scheme);
      await page.goto('/notifications');
      await expect(page.getByRole('heading', { level: 1, name: 'Notifications' })).toBeVisible();

      // Channels: kind icon plus word, target, enabled switch, last delivery.
      const channels = page.getByRole('table', { name: 'Channels with their kind, state and last delivery' });
      await expect(channels.locator('tbody tr')).toHaveCount(3);
      await expect(page.getByText('3 channels')).toBeVisible();
      const emailRow = channels.locator('tbody tr').filter({ hasText: 'Night crew (fictional)' });
      await expect(emailRow.locator('.co-kind svg')).toHaveCount(1);
      await expect(emailRow).toContainText('E-mail');
      await expect(emailRow).toContainText('Relay relay.example.test:587');
      await expect(emailRow).toContainText('1 recipient');
      await expect(emailRow).toContainText('Sent');
      const hookRow = channels.locator('tbody tr').filter({ hasText: 'Ops hook (fictional)' });
      await expect(hookRow).toContainText('URL set');
      await expect(hookRow).toContainText('Host hooks.example.test');
      const slackRow = channels.locator('tbody tr').filter({ hasText: 'MSP Slack (fictional)' });
      await expect(slackRow).toContainText('Failed');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('notifications-channels', width, scheme), fullPage: width > 390 });

      // Rules: channel, scope in words, events as chips.
      await page.getByRole('tab', { name: 'Rules' }).click();
      const rules = page.getByRole('table', { name: 'Rules with their channel, scope and events' });
      await expect(rules.locator('tbody tr')).toHaveCount(2);
      await expect(rules.locator('tbody tr').filter({ hasText: 'Every job of every client' })).toHaveCount(1);
      await expect(rules.locator('tbody tr').filter({ hasText: 'Night crew (fictional)' })).toContainText('Failed');
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('notifications-rules', width, scheme), fullPage: width > 390 });

      // History: two pages behind a cursor, a badge per status.
      await page.getByRole('tab', { name: 'History' }).click();
      const history = page.getByRole('table', { name: 'Notifications with their status, subject, channel, attempts and error' });
      await expect(history.locator('tbody tr')).toHaveCount(2);
      await expect(history.locator('tbody tr').filter({ hasText: 'Veeam nightly' }).filter({ hasText: 'Missed' })).toHaveCount(1);
      await page.getByRole('button', { name: 'Show more' }).click();
      await expect(history.locator('tbody tr')).toHaveCount(4);
      await expect(history.locator('tbody tr').filter({ hasText: 'Daily digest of 2026-11-20' })).toHaveCount(1);
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('notifications-history', width, scheme), fullPage: width > 390 });

      // Settings: the digest card.
      await page.goto('/settings');
      await expect(page.getByRole('heading', { level: 2, name: 'Daily digest' })).toBeVisible();
      await expect(page.getByLabel('Digest time')).toHaveValue('07:00');
      await expect(page.getByLabel('Time zone')).toHaveValue('Europe/Lisbon');
      await expectAccessible(page);
      await page.screenshot({ path: shot('settings-digest', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

test('notifications: create an e-mail channel, warn about a clear-text login, keep the password write-only', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const store = await installNotificationsApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/notifications');
  await page.getByRole('button', { name: 'New channel' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New channel' });
  await expect(drawer.getByRole('radio', { name: /E-mail/ })).toHaveAttribute('aria-checked', 'true');
  await drawer.getByLabel('Label').fill('On-call (fictional)');
  await drawer.getByLabel('To').fill('crew@example.test');
  await drawer.getByLabel('From address').fill('checkorca@example.test');
  await drawer.getByLabel('Relay host').fill('relay2.example.test');
  // A login without STARTTLS crosses the network in clear text.
  await drawer.getByRole('switch', { name: 'Use STARTTLS' }).click();
  await drawer.getByLabel('User name').fill('alerts');
  await expect(drawer.getByTestId('cleartext-warning')).toBeVisible();
  await drawer.getByLabel('Relay password').fill('synthetic-relay-password');
  await drawer.getByRole('button', { name: 'Create channel' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Channel created');
  await expect(drawer).toBeHidden();
  const created = store.calls.find((call) => call.method === 'POST' && call.url === '/api/v1/channels');
  expect(created?.body).toContain('"starttls":false');
  expect(created?.body).toContain('"secret":"synthetic-relay-password"');
  // The CSRF header rides on every state change.
  expect(created?.headers['x-csrf-token']).toBe(ADMIN.csrf_token);
  expect(store.channels.some((item) => item.label === 'On-call (fictional)')).toBe(true);
  // The edit drawer never shows the password again: the masked hint only.
  const row = page.getByRole('table', { name: 'Channels with their kind, state and last delivery' }).locator('tbody tr').filter({ hasText: 'On-call (fictional)' });
  await row.click();
  const edit = page.getByRole('dialog', { name: 'Edit channel' });
  await expect(edit.getByText(/Stored password: \*/)).toBeVisible();
  expect(await edit.getByLabel('Relay password').inputValue()).toBe('');
  await expect(edit).not.toContainText('synthetic-relay-password');
  await expect(page.locator('body')).not.toContainText('synthetic-relay-password');
  expect(errors()).toEqual([]);
});

test('notifications: a webhook URL is checked first, refused targets stay inline, and the Teams hint says MessageCard', async ({ page }) => {
  const errors = watchConsole(page, EXPECTED);
  await stubApi(page, { me: ADMIN });
  const store = await installNotificationsApi(page);
  await setView(page, 390, 'dark');
  await page.goto('/notifications');
  await page.getByRole('button', { name: 'New channel' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New channel' });
  await drawer.getByRole('radio', { name: /Teams/ }).click();
  await expect(drawer).toContainText('MessageCard');
  expect((await drawer.textContent()) ?? '').not.toMatch(/recommend/i);
  await drawer.getByRole('radio', { name: /Webhook/ }).click();
  await drawer.getByLabel('Label').fill('Ops hook 2 (fictional)');
  // A private target is refused before the save; the sentence names the
  // address, never the path, and no channel is created.
  await drawer.getByLabel('Webhook URL').fill('http://10.0.0.5/services/T000');
  await drawer.getByRole('button', { name: 'Create channel' }).click();
  await expect(drawer.getByText(/10\.0\.0\.5 is a private address/)).toBeVisible();
  expect(store.calls.filter((call) => call.method === 'POST' && call.url === '/api/v1/channels')).toHaveLength(0);
  // A public URL passes the check and is never shown back: only the host.
  await drawer.getByLabel('Webhook URL').fill('https://hooks.example.test/services/T000/B000/XXXX');
  await drawer.getByRole('button', { name: 'Create channel' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Channel created');
  const row = page.getByRole('table', { name: 'Channels with their kind, state and last delivery' }).locator('tbody tr').filter({ hasText: 'Ops hook 2 (fictional)' });
  await expect(row).toContainText('Host hooks.example.test');
  await expect(page.locator('body')).not.toContainText('/services/T000');
  await expectNoHorizontalOverflow(page);
  await expectAccessible(page);
  expect(errors()).toEqual([]);
});

test('notifications: a test answers inline, and the failed answer never changes the last delivery', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  await installNotificationsApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/notifications');
  const table = page.getByRole('table', { name: 'Channels with their kind, state and last delivery' });
  const email = table.locator('tbody tr').filter({ hasText: 'Night crew (fictional)' });
  await email.getByRole('button', { name: 'Send a test' }).click();
  const note = email.getByTestId('test-result');
  await expect(note).toContainText('Test delivered');
  await expect(note).toContainText('The relay accepted the test message.');
  // The badge keeps the stored delivery; a test writes nothing.
  await expect(email).toContainText('Sent');
  const slack = table.locator('tbody tr').filter({ hasText: 'MSP Slack (fictional)' });
  await slack.getByRole('button', { name: 'Send a test' }).click();
  const failedNote = slack.getByTestId('test-result');
  await expect(failedNote).toContainText('Test failed');
  await expect(failedNote).toContainText('The target answered 404 and no 2xx counts as sent.');
  await expect(slack).toContainText('Failed');
  await expectAccessible(page);
  await page.screenshot({ path: shot('notifications-test', 1440, 'light') });
  expect(errors()).toEqual([]);
});

test('notifications: a rule is created with pickers, and the digest event needs the scope All clients', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page);
  const store = await installNotificationsApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/notifications?tab=rules');
  await page.getByRole('button', { name: 'New rule' }).first().click();
  const drawer = page.getByRole('dialog', { name: 'New rule' });
  await drawer.getByRole('combobox', { name: 'Channel' }).click();
  await page.getByRole('option', { name: 'Ops hook (fictional)' }).click();
  await drawer.getByRole('button', { name: 'One client' }).click();
  await drawer.getByRole('combobox', { name: 'Client' }).click();
  await page.getByRole('option', { name: 'Harbourside Dental (fictional)' }).click();
  await expect(drawer.getByRole('checkbox', { name: /Digest/ })).toBeDisabled();
  await drawer.getByRole('checkbox', { name: /Missed/ }).click();
  await drawer.getByRole('button', { name: 'Create rule' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Rule created');
  const created = store.calls.find((call) => call.method === 'POST' && call.url === '/api/v1/channel-rules');
  expect(created?.body).toContain('"scope":"client"');
  expect(store.rules.some((item) => item.channel_id === 'ch100000-0000-4000-8000-000000000002' && item.scope === 'client')).toBe(true);
  // The new rule is in the table with its channel and events.
  const rules = page.getByRole('table', { name: 'Rules with their channel, scope and events' });
  await expect(rules.locator('tbody tr').filter({ hasText: 'Ops hook (fictional)' }).filter({ hasText: 'Harbourside Dental (fictional)' })).toHaveCount(1);
  await expectAccessible(page);
  expect(errors()).toEqual([]);
});

test('notifications: the history filters by status and the System page links to the failed ones', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const store = await installNotificationsApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/notifications?tab=history');
  const history = page.getByRole('table', { name: 'Notifications with their status, subject, channel, attempts and error' });
  await expect(history.locator('tbody tr')).toHaveCount(2);
  await page.getByRole('combobox', { name: 'Status' }).click();
  await page.getByRole('option', { name: 'Failed' }).click();
  await expect(history.locator('tbody tr')).toHaveCount(1);
  await expect(history.locator('tbody tr')).toContainText('Failed');
  expect(store.calls.some((call) => call.url.includes('status=failed'))).toBe(true);
  await expect(page).toHaveURL(/tab=history&status=failed/);
  // The System page's failed link lands on the same filtered history.
  await page.goto('/system');
  await page.getByRole('link', { name: 'Open the failed notifications' }).click();
  await expect(page).toHaveURL(/tab=history&status=failed/);
  await expect(history.locator('tbody tr')).toHaveCount(1);
  expect(errors()).toEqual([]);
});

test('notifications: the digest settings save what changed, with the CSRF header', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const store = await installNotificationsApi(page);
  await setView(page, 1440, 'light');
  await page.goto('/settings');
  await page.getByLabel('Digest time').fill('08:30');
  const zone = page.getByRole('combobox', { name: 'Time zone' });
  await zone.click();
  await zone.fill('Madrid');
  await page.getByRole('option', { name: 'Europe/Madrid' }).click();
  await page.getByRole('switch', { name: 'Remind after 24 hours' }).click();
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Settings saved');
  const patch = store.calls.find((call) => call.method === 'PATCH' && call.url === '/api/v1/settings');
  expect(JSON.parse(String(patch?.body))).toEqual({ digest_time_local: '08:30', digest_timezone: 'Europe/Madrid', reminder_24h: true });
  expect(patch?.headers['x-csrf-token']).toBe(ADMIN.csrf_token);
  expect(errors()).toEqual([]);
});

test('notifications: hostile names, labels and error sentences stay text', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const hostile: NotificationOut = {
    id: 'n1000000-0000-4000-8000-000000000009',
        channel_id: 'ch100000-0000-4000-8000-000000000001',
        channel_label: 'Crew <script>window.__pwned = 21</script>',
        channel_kind: 'email',
        event: 'missed',
        status: 'failed',
        attempts: 2,
        error: 'The relay said <img src=x onerror="window.__pwned = 22"> no.',
        flip_id: 'f1000000-0000-4000-8000-000000000001',
        job_id: 'j1000000-0000-4000-8000-000000000001',
        job_name: 'Veeam <a href="javascript:window.__pwned = 23">nightly</a>',
        client_id: 'c1000000-0000-4000-8000-000000000001',
        client_name: 'Harbourside <script>window.__pwned = 24</script> Dental',
        digest_day: null,
    created_at: '2026-11-20T08:07:00Z',
    last_attempt_at: '2026-11-20T08:07:04Z',
    next_attempt_at: null,
    sent_at: null,
  };
  await installNotificationsApi(page, { channels: [], rules: [], notifications: [hostile] });
  await setView(page, 1440, 'light');
  await page.goto('/notifications?tab=history');
  await expect(page.getByRole('table', { name: 'Notifications with their status, subject, channel, attempts and error' })).toContainText('The relay said');
  await expectNothingRan(page);
  await expectAccessible(page);
  expect(errors()).toEqual([]);
});

test('notifications: the technician reads without any control', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: TECHNICIAN });
  await installNotificationsApi(page);
  await setView(page, 768, 'dark');
  await page.goto('/notifications');
  const channels = page.getByRole('table', { name: 'Channels with their kind, state and last delivery' });
  await expect(channels.locator('tbody tr')).toHaveCount(3);
  await expect(page.getByText('Admins create and change channels and rules; technicians can read them.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'New channel' })).toHaveCount(0);
  await expect(page.getByRole('switch')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Send a test' })).toHaveCount(0);
  // The Settings address is not the technician's.
  await page.goto('/settings');
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
  expect(errors()).toEqual([]);
});
