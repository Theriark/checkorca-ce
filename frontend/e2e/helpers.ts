/* Shared pieces of the Playwright run: widths, schemes, API stubs (the
   preview server has no backend), the axe check and the screenshot path. */
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export const WIDTHS = [1440, 768, 390] as const;
export const SCHEMES = ['light', 'dark'] as const;
export type Scheme = (typeof SCHEMES)[number];

export const ADMIN = {
  id: '11111111-1111-4111-8111-111111111111',
  email: 'checkorca.admin@example.com',
  role: 'admin',
  csrf_token: 'csrf-admin',
};

export const TECHNICIAN = {
  id: '22222222-2222-4222-8222-222222222222',
  email: 'checkorca.technician@example.com',
  role: 'technician',
  csrf_token: 'csrf-technician',
};

const PROBLEM_HEADERS = { 'content-type': 'application/problem+json', 'x-request-id': 'req-e2e' };

/** Stub the auth routes: me (session), setup-state and login. */
export async function stubApi(
  page: Page,
  options: { readonly me?: typeof ADMIN | null; readonly needsFirstRun?: boolean; readonly loginStatus?: number } = {},
) {
  const me = options.me ?? null;
  await page.route('**/api/v1/auth/me', (route) => {
    if (me) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(me) });
    }
    return route.fulfill({ status: 401, headers: PROBLEM_HEADERS, body: JSON.stringify({ title: 'Unauthorized', status: 401 }) });
  });
  await page.route('**/api/v1/auth/setup-state', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ needs_first_run: options.needsFirstRun ?? false }) }),
  );
  await page.route('**/api/v1/auth/login', (route) => {
    const status = options.loginStatus ?? 401;
    if (status === 200) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user: { ...ADMIN, disabled: false, locked_until: null, created_at: '2026-11-18T00:00:00Z' }, csrf_token: 'csrf-login' }),
      });
    }
    return route.fulfill({ status, headers: PROBLEM_HEADERS, body: JSON.stringify({ title: 'Unauthorized', status, request_id: 'req-e2e' }) });
  });
  await page.route('**/api/v1/auth/logout', (route) => route.fulfill({ status: 204 }));
}

export async function setView(page: Page, width: number, scheme: Scheme) {
  await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
}

/** Axe (WCAG 2.1 A and AA) must report nothing. */
export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

/** Nothing overflows the viewport horizontally. */
export async function expectNoHorizontalOverflow(page: Page) {
  const report = await page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth - window.innerWidth;
    const offenders = Array.from(document.querySelectorAll('body *'))
      .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 0.5)
      .slice(0, 8)
      .map((element) => `${element.tagName.toLowerCase()}.${Array.from(element.classList).join('.')} right=${Math.round(element.getBoundingClientRect().right)}`);
    return { overflow, offenders };
  });
  expect(report.overflow, report.offenders.join('\n')).toBeLessThanOrEqual(0);
}

/** The brand file really loaded (not a broken image) and is wide enough. */
export async function expectLogo(page: Page, name: string, minWidth: number) {
  const logo = page.getByRole('img', { name }).first();
  await expect(logo).toBeVisible();
  // The theme can swap the file right after the first paint: wait for the load.
  await expect
    .poll(() => logo.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0), { timeout: 5000 })
    .toBe(true);
  const box = await logo.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(minWidth);
}

export function shot(name: string, width: number, scheme: Scheme): string {
  return `screenshots/${name}-${width}-${scheme}.png`;
}
