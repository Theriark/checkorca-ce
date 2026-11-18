import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// The ui-standard widths, in both colour schemes.
const WIDTHS = [1440, 768, 390] as const;
const SCHEMES = ['light', 'dark'] as const;

for (const scheme of SCHEMES) {
  for (const width of WIDTHS) {
    test(`shell page at ${width} px, ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');

      const logo = page.getByRole('img', { name: 'Checkorca-CE' });
      await expect(logo).toBeVisible();
      // The brand file really loaded: not a broken image.
      const loaded = await logo.evaluate(
        (image: HTMLImageElement) => image.complete && image.naturalWidth > 0,
      );
      expect(loaded).toBe(true);
      const box = await logo.boundingBox();
      // Brand minimum: the horizontal lockup is at least 120 px wide.
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(120);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Morning check');

      // Nothing overflows the viewport horizontally.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      expect(results.violations).toEqual([]);

      await page.screenshot({
        path: `screenshots/shell-${width}-${scheme}.png`,
        fullPage: true,
      });
    });
  }
}

test('the favicon is a brand file', async ({ request }) => {
  const response = await request.get('/brand/favicon-32x32.png');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('image/png');
});
