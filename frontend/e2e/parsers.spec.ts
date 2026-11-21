import { expect, test, type Page } from '@playwright/test';

import { ACME_PACK, installFakeApi, installIngestApi, installParserApi, packYaml } from './fakeApi';
import { ADMIN, SCHEMES, TECHNICIAN, WIDTHS, expectAccessible, expectNoHorizontalOverflow, setView, shot, stubApi, watchConsole } from './helpers';

const SAMPLE = [
  'From: Backup Robot <backup@example.com>',
  'To: alerts@example.com',
  'Subject: Nightly file backup failed',
  'Date: Fri, 20 Nov 2026 02:14:00 +0000',
  'Message-ID: <bench-e2e-0001@example.com>',
  '',
  'Synthetic sample for the test bench.',
  'Job: Nightly file backup',
  'Client: Blue Fern Studio (fictional)',
  'Status: Failed',
  'Error: disk quota exceeded on target',
  '<script>window.__pwned = 1</script>',
  '',
].join('\r\n');

async function installAll(page: Page) {
  const fake = await installFakeApi(page);
  const ingest = await installIngestApi(page);
  const parsers = await installParserApi(page, { fake, ingest });
  return { fake, ingest, parsers };
}

/** Replace the whole document of the CodeMirror editor: select all, then
 *  paste the text (CodeMirror reads the clipboard data of the paste event). */
async function replaceYaml(page: Page, yaml: string) {
  const content = page.locator('.cm-content');
  await content.click();
  await page.keyboard.press('ControlOrMeta+a');
  await content.evaluate((element, text) => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, yaml);
  await expect(content).toContainText(yaml.split('\n')[0] ?? '');
}

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`parsers list and a built-in pack at ${width} px, ${scheme}: badges with icon and word, the enabled switch, the bundled read-only editor`, async ({ page }) => {
      const errors = watchConsole(page);
      await stubApi(page, { me: ADMIN });
      const { parsers } = await installAll(page);
      await setView(page, width, scheme);
      await page.goto('/parsers');
      await expect(page.getByRole('heading', { level: 1, name: 'Parsers' })).toBeVisible();
      const table = page.getByRole('table', { name: 'Parser packs with their vendor, version, source and status' });
      await expect(table.locator('tbody tr')).toHaveCount(2);
      await expect(page.getByText('2 packs')).toBeVisible();
      const generic = table.locator('tbody tr').filter({ hasText: 'generic-keywords' });
      await expect(generic).toContainText('Generic');
      await expect(generic).toContainText('Built-in');
      await expect(generic).toContainText('Unverified-synthetic');
      await expect(generic.locator('.co-badge svg')).toHaveCount(1);
      await expect(generic.getByRole('switch', { name: 'Enabled: generic-keywords' })).toBeChecked();
      const acme = table.locator('tbody tr').filter({ hasText: 'acme-backup' });
      await expect(acme).toContainText('Custom');
      await expect(acme.getByRole('switch', { name: 'Enabled: acme-backup' })).not.toBeChecked();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('parsers', width, scheme), fullPage: width > 390 });
      // The switch enables the pack from the worker's next tick.
      await acme.getByRole('switch', { name: 'Enabled: acme-backup' }).click();
      await expect(page.locator('.co-toast--success').last()).toContainText('Pack enabled');
      await expect(page.locator('.co-toast--success').last()).toContainText('next tick');
      expect(parsers.calls.some((call) => call.method === 'POST' && call.url.endsWith('/acme-backup/enable'))).toBe(true);
      await expect(acme.getByRole('switch', { name: 'Enabled: acme-backup' })).toBeChecked();

      // The built-in pack: read-only, the editor bundled (no CDN script).
      await generic.getByRole('link', { name: 'generic-keywords' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'generic-keywords' })).toBeVisible();
      await expect(page.getByText('Read-only', { exact: true })).toBeVisible();
      await expect(page.getByText('Built-in packs are read-only.', { exact: false })).toBeVisible();
      const content = page.locator('.cm-content');
      await expect(content).toHaveAttribute('contenteditable', 'false');
      await expect(content).toHaveAttribute('aria-label', 'Pack YAML editor');
      await expect(content).toContainText('id: generic-keywords');
      await expect(page.locator('.cm-gutters')).toBeVisible();
      expect(await page.locator('script[src]').evaluateAll((nodes) => nodes.map((node) => (node as HTMLScriptElement).src).filter((src) => !src.startsWith(location.origin)))).toEqual([]);
      await expect(page.getByRole('button', { name: 'Save pack' })).toHaveCount(0);
      await expect(page.getByRole('switch', { name: 'Enabled' })).toBeChecked();
      await expect(page.getByRole('button', { name: 'Export YAML' })).toBeVisible();
      await expect(page.getByLabel('Mail', { exact: true })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectAccessible(page);
      await page.screenshot({ path: shot('pack-detail', width, scheme), fullPage: width > 390 });
      expect(errors()).toEqual([]);
    });
  }
}

for (const [width, scheme] of [
  [1440, 'light'],
  [390, 'dark'],
] as const) {
  test(`parsers: a custom pack is edited in place; the bench runs the edited YAML; a 422 lands at its line; the save succeeds after the fix (${width} px, ${scheme})`, async ({ page }) => {
    // The 422 of the first save is expected.
    const errors = watchConsole(page, [422]);
    await stubApi(page, { me: ADMIN });
    const { parsers } = await installAll(page);
    await setView(page, width, scheme);
    await page.goto(`/parsers/packs/${ACME_PACK.id}`);
    await expect(page.getByRole('heading', { level: 1, name: ACME_PACK.id })).toBeVisible();
    const content = page.locator('.cm-content');
    await expect(content).toHaveAttribute('contenteditable', 'true');
    await expect(page.getByRole('button', { name: 'Save pack' })).toBeDisabled();
    await expect(page.getByText(/\d+ lines/)).toBeVisible();
    // An edit that adds a rule, still at the stored version: Save is live; the
    // bench says it runs the edited YAML and claims the mail with it.
    await replaceYaml(page, packYaml(ACME_PACK.id, 1, 'Acme Backup (fictional)', "  - {status: warning, regex: '(?i)\\bwarn'}"));
    await expect(content).toContainText('status: warning');
    await expect(page.getByText('Unsaved changes')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save pack' })).toBeEnabled();
    await expect(page.getByText('The bench runs the YAML in the editor in place of the stored pack, so you can test before saving.')).toBeVisible();
    await page.getByRole('button', { name: 'Use a sample mail' }).click();
    await page.getByRole('button', { name: 'Run the packs' }).click();
    const answer = page.getByRole('region', { name: 'What the packs made of it' });
    await expect(answer).toBeVisible();
    await expect(answer.locator('.co-bench__claimant')).toHaveText(ACME_PACK.id);
    await expect(answer.getByRole('table', { name: 'Scores' }).locator('tbody tr').filter({ hasText: ACME_PACK.id })).toContainText('edited');
    const benchCall = parsers.calls.find((call) => call.method === 'POST' && call.url.endsWith('/packs/test'));
    expect(benchCall?.body).toContain('"pack":"id: acme-backup');
    await expectAccessible(page);
    await page.screenshot({ path: shot('pack-bench-edited', width, scheme), fullPage: true });
    // A rule that does not compile: the engine loads the edited pack before
    // the run, so the bench answers 422 with the issue at its path; it is
    // shown in the bench, not as an error page.
    await replaceYaml(page, packYaml(ACME_PACK.id, 1, 'Acme Backup (fictional)', "  - {status: warning, regex: '('}"));
    await expect(content).toContainText("regex: '('");
    await page.getByRole('button', { name: 'Run the packs' }).click();
    const benchIssue = page.locator('.co-bench__form').getByRole('alert');
    await expect(benchIssue).toContainText('status_rules › 0 › regex');
    await expect(benchIssue).toContainText('missing )');
    // The save: two issues, each at its path and line, marked in the editor.
    await page.getByRole('button', { name: 'Save pack' }).click();
    const issues = page.getByRole('alert').filter({ hasText: 'The pack does not load' });
    await expect(issues).toBeVisible();
    await expect(issues).toContainText('At version');
    await expect(issues).toContainText('line 2');
    await expect(issues).toContainText('must be higher than 1.');
    await expect(issues).toContainText('At status_rules › 0 › regex');
    await expect(issues).toContainText('line 16');
    await expect(issues).toContainText('is not a valid pattern: missing ).');
    await expect(page.locator('.cm-lint-marker-error')).toHaveCount(2);
    await expectNoHorizontalOverflow(page);
    await expectAccessible(page);
    await page.screenshot({ path: shot('pack-editor-issues', width, scheme), fullPage: true });
    // The fix saves and the issues go.
    await replaceYaml(page, packYaml(ACME_PACK.id, 2, 'Acme Backup (fictional)'));
    await expect(content).toContainText('version: 2');
    await page.getByRole('button', { name: 'Save pack' }).click();
    await expect(page.locator('.co-toast--success').last()).toContainText('Pack saved');
    await expect(issues).toHaveCount(0);
    await expect(page.locator('.cm-lint-marker-error')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save pack' })).toBeDisabled();
    await expect(page.getByText('Unsaved changes')).toHaveCount(0);
    expect(parsers.packs.find((item) => item.id === ACME_PACK.id)?.version).toBe(2);
    await expect(page.locator('.co-kv').filter({ hasText: 'Version' })).toContainText('2');
    // Discard restores the stored text.
    await replaceYaml(page, 'id: acme-backup\nversion: 3\n');
    await expect(page.getByText('Unsaved changes')).toBeVisible();
    await page.getByRole('button', { name: 'Discard changes' }).click();
    await expect(content).toContainText("vendor: Acme Backup (fictional)");
    await expect(page.getByRole('button', { name: 'Save pack' })).toBeDisabled();
    expect(errors()).toEqual([]);
  });
}

for (const [width, scheme] of [
  [768, 'light'],
  [390, 'dark'],
] as const) {
  test(`parsers: the test bench waits out a busy bench (503) and highlights the spans in the mail as read; a script tag stays text (${width} px, ${scheme})`, async ({ page }) => {
    // The 503 of the busy bench is expected.
    const errors = watchConsole(page, [503]);
    await stubApi(page, { me: ADMIN });
    const { parsers } = await installAll(page);
    await setView(page, width, scheme);
    await page.goto('/parsers/bench');
    await expect(page.getByRole('heading', { level: 1, name: 'Test bench' })).toBeVisible();
    await expect(page.getByText('Run the packs to see the answer here.')).toBeVisible();
    await page.getByRole('button', { name: 'Run the packs' }).click();
    await expect(page.getByText('Paste or upload a mail first.')).toBeVisible();
    await page.getByLabel('Mail', { exact: true }).fill(SAMPLE);
    parsers.busyRuns = 1;
    await page.getByRole('button', { name: 'Run the packs' }).click();
    // Busy: a note with the wait and a button, never an error page; then the retry answers.
    const busy = page.getByRole('status').filter({ hasText: 'The bench is busy' });
    await expect(busy).toBeVisible();
    await expect(busy).toContainText('Trying again in 1 s.');
    await expect(busy.getByRole('button', { name: 'Try again now' })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.screenshot({ path: shot('bench-busy', width, scheme) });
    const answer = page.getByRole('region', { name: 'What the packs made of it' });
    await expect(answer).toBeVisible({ timeout: 10_000 });
    await expect(busy).toHaveCount(0);
    expect(parsers.calls.filter((call) => call.method === 'POST' && call.url.endsWith('/packs/test'))).toHaveLength(2);
    await expect(answer.locator('.co-bench__claimant')).toHaveText('generic-keywords');
    await expect(answer).toContainText('Parsed');
    const scores = answer.getByRole('table', { name: 'Scores' });
    await expect(scores.locator('tbody tr')).toHaveCount(1);
    await expect(answer).toContainText('Result 1');
    await expect(answer).toContainText('disk quota exceeded on target');
    const body = page.getByTestId('bench-body');
    await expect(body.locator('mark[data-field="job_name"]')).toContainText('Nightly file backup');
    await expect(body.locator('mark[data-field="client_hint"]')).toContainText('Blue Fern Studio (fictional)');
    await expect(body.locator('mark[data-field="status"]')).toContainText('Failed');
    await expect(body.locator('mark[data-field="details.error"]')).toContainText('disk quota exceeded on target');
    await expect(body).toContainText('<script>window.__pwned = 1</script>');
    expect(await body.locator('script').count()).toBe(0);
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    await expectNoHorizontalOverflow(page);
    await expectAccessible(page);
    await page.screenshot({ path: shot('bench', width, scheme), fullPage: true });
    // A mail no pack claims.
    await page.getByLabel('Mail', { exact: true }).fill('From: a@example.com\r\nSubject: Lunch menu\r\n\r\nSoup of the day.\r\n');
    await page.getByRole('button', { name: 'Run the packs' }).click();
    await expect(answer).toContainText('No pack claims this mail');
    await expect(answer).toContainText('Unmatched');
    await expect(answer).toContainText('No result.');
    expect(errors()).toEqual([]);
  });
}

test('parsers: import refuses a pack with issues, by path, and opens a good one', async ({ page }) => {
  const errors = watchConsole(page, [422]);
  await stubApi(page, { me: ADMIN });
  await installAll(page);
  await setView(page, 1440, 'dark');
  await page.goto('/parsers');
  await page.getByRole('button', { name: 'Import pack' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Import a parser pack' });
  await dialog.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(dialog.getByText('Choose a file first.')).toBeVisible();
  await dialog.getByLabel('Pack YAML file').setInputFiles({ name: 'bad.yaml', mimeType: 'application/yaml', buffer: Buffer.from(packYaml('Bad Id', 0, 'Nobody')) });
  await dialog.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('The pack was not imported');
  await expect(dialog.getByRole('alert')).toContainText('id: is not a pack id');
  await expect(dialog.getByRole('alert')).toContainText('version: must be a whole number from 1.');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/pack-import-issues-1440-dark.png' });
  await dialog.getByLabel('Pack YAML file').setInputFiles({ name: 'cove-mail.yaml', mimeType: 'application/yaml', buffer: Buffer.from(packYaml('cove-mail', 1, 'Cove (fictional)')) });
  await dialog.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(page.locator('.co-toast--success').last()).toContainText('Pack imported');
  await expect(page).toHaveURL(/\/parsers\/packs\/cove-mail$/);
  await expect(page.getByRole('heading', { level: 1, name: 'cove-mail' })).toBeVisible();
  await expect(page.getByText('Custom', { exact: true }).first()).toBeVisible();
  expect(errors()).toEqual([]);
});

test('parsers: loading, empty and error states are designed', async ({ page }) => {
  await stubApi(page, { me: ADMIN });
  const fake = await installFakeApi(page);
  const ingest = await installIngestApi(page);
  await installParserApi(page, { fake, ingest }, { packs: [] });
  await setView(page, 1440, 'light');
  await page.goto('/parsers');
  await expect(page.getByRole('heading', { level: 3, name: 'No parser packs' })).toBeVisible();
  await expect(page.locator('.co-empty').getByRole('button', { name: 'Import pack' })).toBeVisible();
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/parsers-empty-1440-light.png' });

  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/packs?**', async (route) => {
    await gate;
    await route.fulfill({ status: 500, headers: { 'content-type': 'application/problem+json' }, body: JSON.stringify({ title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-e2e-500' }) });
  });
  await page.reload();
  await expect(page.locator('tbody[aria-busy="true"]')).toBeVisible();
  await page.screenshot({ path: 'screenshots/parsers-loading-1440-light.png' });
  release();
  await expect(page.getByRole('alert')).toContainText('req-e2e-500');
  await expectAccessible(page);
  await page.screenshot({ path: 'screenshots/parsers-error-1440-light.png' });
  // An unknown pack inside the shell.
  await page.unroute('**/api/v1/packs?**');
  await page.goto('/parsers/packs/nope');
  await expect(page.getByRole('heading', { level: 1, name: 'Pack not found' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'All packs' })).toBeVisible();
});

test('parsers: the technician has the same screens', async ({ page }) => {
  await stubApi(page, { me: TECHNICIAN });
  await installAll(page);
  await setView(page, 390, 'light');
  await page.goto('/parsers');
  await expect(page.getByRole('heading', { level: 1, name: 'Parsers' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import pack' })).toBeVisible();
  await page.getByRole('link', { name: 'Test bench' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Test bench' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.goto(`/parsers/packs/${ACME_PACK.id}`);
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.getByRole('button', { name: 'Save pack' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
