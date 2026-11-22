import { expect, test } from '@playwright/test';

import { installFakeApi } from './fakeApi';
import { HOSTILE_CLIENT_NAME, HOSTILE_JOB_NAME, installDashboardApi } from './fakeDashboard';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoContainerOverflow, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

// The digest fixture carries a script on purpose; the sandboxed frame refuses
// to run it and Chromium says so on the console. Nothing else may log.
const SANDBOX_REFUSAL = [/Blocked script execution in 'about:srcdoc'/, /sandboxed and the 'allow-scripts' permission is not set/];

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`morning check at ${width} px, ${scheme}: numbers, ribbon, attention, trend, breakdown, activity`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      const fake = await installFakeApi(page);
      await installDashboardApi(page, { fake });
      await setView(page, width, scheme);
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1, name: 'Morning check' })).toBeVisible();
      // Five stat cards with a number, the change and a sparkline; the ring.
      const cards = page.getByTestId('stat-cards').locator('.co-stat');
      await expect(cards).toHaveCount(5);
      await expect(cards.first()).toContainText('9');
      await expect(cards.first()).toContainText('+2 vs yesterday');
      await expect(page.getByTestId('stat-cards').locator('.co-sparkline')).toHaveCount(5);
      await expect(page.getByRole('img', { name: /Coverage: 69 percent, 9 of 13 verified/ })).toBeVisible();
      await expect(page.getByTestId('seed-label')).toContainText('Seed data');
      // The ribbon: SVG rows with hollow rings and gap lines above the phone
      // width, status chips at 390 px.
      if (width > 390) {
        const ribbon = page.getByTestId('night-ribbon');
        await expect(ribbon.locator('.co-nr__row-svg')).toHaveCount(3);
        await expect(ribbon.locator('.co-nr__ring--hollow')).toHaveCount(2);
        await expect(ribbon.locator('.co-nr__gap')).toHaveCount(2);
        await expect(ribbon.locator('.co-nr__row-svg .co-nr__morning')).toHaveCount(3);
        // Reduced motion (setView asks for it): the hollow ring does not pulse.
        const animation = await ribbon.locator('.co-nr__ring--hollow').first().evaluate((element) => getComputedStyle(element).animationName);
        expect(animation).toBe('none');
        await expect(page.getByTestId('ribbon-chips')).toHaveCount(0);
        // The drawing never leaves its lane.
        await expectNoContainerOverflow(page, ['.co-nr__lane', '.co-nr__axis']);
      } else {
        const chips = page.getByTestId('ribbon-chips');
        await expect(chips).toBeVisible();
        await expect(chips.locator('.co-nrc__chip')).toHaveCount(8);
        await expect(chips.locator('.co-nrc__chip[data-state="missed"] .co-badge svg')).toHaveCount(1);
        await expect(page.getByTestId('night-ribbon')).toHaveCount(0);
      }
      // Needs attention: silent first, then failed, then warning; names are text.
      const attention = page.getByRole('list', { name: 'Needs attention' });
      const rows = attention.getByRole('listitem');
      await expect(rows).toHaveCount(4);
      await expect(rows.nth(0)).toHaveAttribute('data-state', 'missed');
      await expect(rows.nth(1)).toHaveAttribute('data-state', 'overdue');
      await expect(rows.nth(2)).toHaveAttribute('data-state', 'failed');
      await expect(rows.nth(3)).toHaveAttribute('data-state', 'warning');
      await expect(rows.nth(0)).toContainText(HOSTILE_JOB_NAME);
      await expect(rows.nth(0)).toContainText(HOSTILE_CLIENT_NAME);
      expect(await page.locator('script:not([src])').count()).toBe(0);
      expect(await page.locator('img[onerror]').count()).toBe(0);
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      await expect(rows.nth(2)).toContainText('Acknowledged');
      await expect(rows.nth(2).getByRole('link', { name: 'Open message' })).toBeVisible();
      // Trend, breakdown and activity.
      await expect(page.getByRole('img', { name: /Last 30 days: 30 days/ })).toBeVisible();
      await expect(page.getByRole('list', { name: /Breakdown/ }).locator('.co-bd__row')).toHaveCount(3);
      await expect(page.getByRole('list', { name: 'Activity' }).getByRole('listitem')).toHaveCount(3);
      await expectNoHorizontalOverflow(page);
      await expectNoContainerOverflow(page, ['.co-stat', '.co-ring', '.co-dash__card']);
      await expectAccessible(page);
      await page.screenshot({ path: shot('morning-check', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

test('morning check: problems only narrows the ribbon, acknowledge posts and shows the time, the day export downloads', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: ADMIN });
  const fake = await installFakeApi(page);
  const store = await installDashboardApi(page, { fake });
  await setView(page, 1440, 'light');
  await page.goto('/');
  const ribbon = page.getByTestId('night-ribbon');
  await expect(ribbon.locator('.co-nr__row-svg')).toHaveCount(3);
  await page.getByRole('switch', { name: 'Problems only' }).check();
  await expect.poll(() => store.calls.some((call) => call.url.includes('/dashboard/ribbon') && call.url.includes('problems_only=true'))).toBe(true);
  // The verified-only job (Veeam nightly) is gone; every silent job stays.
  await expect(ribbon.locator('.co-nr__ring--verified')).toHaveCount(2);
  await expect(ribbon.locator('.co-nr__ring--hollow')).toHaveCount(2);
  await page.getByRole('switch', { name: 'Problems only' }).uncheck();
  await expect(ribbon.locator('.co-nr__ring--verified')).toHaveCount(3);

  // Acknowledge the silent job: the API answers the time, the row shows it.
  const first = page.getByRole('list', { name: 'Needs attention' }).getByRole('listitem').first();
  await first.getByRole('button', { name: 'Acknowledge' }).click();
  await expect(page.locator('.co-toast--success')).toContainText('Acknowledged');
  await expect(first).toContainText('Acknowledged');
  await expect(first.getByRole('button', { name: 'Acknowledge' })).toHaveCount(0);
  const post = store.calls.find((call) => call.method === 'POST' && call.url.endsWith('/acknowledge'));
  expect(post?.url).toContain(`/jobs/`);
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/morning-check-acknowledged-1440-light.png' });

  // Pause from the list opens the shared dialog with the job name.
  await first.getByRole('button', { name: 'Pause' }).click();
  await expect(page.getByRole('dialog', { name: new RegExp(`Pause .*copy`) })).toBeVisible();
  await page.keyboard.press('Escape');

  // The day export is a CSV download named after the day.
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export today (CSV)' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^day-\d{4}-\d{2}-\d{2}\.csv$/);
  await expect(page.locator('.co-toast--success').last()).toContainText('Export downloaded');
  expect(store.calls.some((call) => call.url.includes('/exports/day.csv') && /date=\d{4}-\d{2}-\d{2}/.test(call.url))).toBe(true);
  const history = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export last 30 days (CSV)' }).click();
  expect((await history).suggestedFilename()).toMatch(/^history-\d{4}-\d{2}-\d{2}\.csv$/);
  expect(errors()).toEqual([]);
});

for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
  test(`digest preview at ${width} px, ${scheme}: a sandboxed frame without script permission renders the e-mail, the text tab escapes`, async ({ page }) => {
    const errors = watchConsole(page, [], SANDBOX_REFUSAL);
    await stubApi(page, { me: ADMIN });
    const fake = await installFakeApi(page);
    await installDashboardApi(page, { fake });
    await setView(page, width, scheme);
    await page.goto('/');
    await page.getByRole('button', { name: 'Preview the digest' }).click();
    const dialog = page.getByRole('dialog', { name: 'Morning digest' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('1 failed, 2 silent, 1 warning, 9 verified');
    const frame = dialog.getByTestId('digest-frame');
    await expect(frame).toHaveAttribute('sandbox', '');
    await expect(frame).not.toHaveAttribute('src', /./);
    const inner = page.frameLocator('[data-testid="digest-frame"]');
    await expect(inner.locator('body')).toContainText('Morning check');
    await expect(inner.locator('body')).toContainText(HOSTILE_JOB_NAME);
    await expect(inner.locator('body')).not.toContainText('pwned');
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    await expectAccessible(page);
    await page.screenshot({ path: shot('digest-preview', width, scheme) });
    await dialog.getByRole('tab', { name: 'As text' }).click();
    await expect(dialog.getByTestId('digest-text')).toContainText('<script>alert(1)</script>');
    expect(await dialog.locator('script').count()).toBe(0);
    expect(errors()).toEqual([]);
  });
}

test('morning check: the first-run checklist, then the error state with a retry', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  await installFakeApi(page, { clients: [], jobs: [] });
  await installDashboardApi(page, { empty: true });
  await setView(page, 1440, 'light');
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 3, name: 'Your morning check starts here' })).toBeVisible();
  await expect(page.locator('.co-empty__steps li')).toHaveCount(4);
  await expect(page.getByRole('link', { name: 'Create the first client' })).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/morning-check-empty-1440-light.png', fullPage: true });

  await page.unroute('**/api/v1/dashboard/today');
  await page.route('**/api/v1/dashboard/today', (route) =>
    route.fulfill({ status: 503, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Service Unavailable', status: 503, detail: 'The database did not answer in time.', request_id: 'req-e2e-503' }) }),
  );
  await page.reload();
  await expect(page.getByRole('alert').first()).toContainText('The database did not answer in time.');
  await expect(page.getByRole('alert').first()).toContainText('req-e2e-503');
  await expect(page.getByRole('button', { name: 'Try again' }).first()).toBeVisible();
  await page.screenshot({ path: 'screenshots/morning-check-error-1440-light.png' });
});

test('morning check: the technician has the same page, at tablet width in dark', async ({ page }) => {
  const errors = watchConsole(page);
  await stubApi(page, { me: TECHNICIAN });
  const fake = await installFakeApi(page);
  await installDashboardApi(page, { fake });
  await setView(page, 768, 'dark');
  await page.goto('/');
  await expect(page.getByTestId('night-ribbon').locator('.co-nr__ring--hollow')).toHaveCount(2);
  await expect(page.getByRole('list', { name: 'Needs attention' }).getByRole('button', { name: 'Acknowledge' }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export today (CSV)' })).toBeVisible();
  await expectAccessible(page);
  expect(errors()).toEqual([]);
});
