import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import manifest from '../package.json';
import { App } from './App';
import { APP_VERSION, PRODUCT_NAME } from './strings';

afterEach(cleanup);

describe('App shell', () => {
  it('shows the logo with the product name as its text', () => {
    render(<App />);
    const logo = screen.getByRole('img', { name: PRODUCT_NAME });
    expect(logo.getAttribute('src')).toBe('/brand/logo-horizontal-600x200.png');
    expect(logo.getAttribute('srcset')).toContain('logo-horizontal-1200x400.png 2x');
  });

  it('has one main heading, the version and the landmarks', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Morning check');
    expect(screen.getByText(APP_VERSION)).toBeTruthy();
    expect(screen.getByRole('banner')).toBeTruthy();
    expect(screen.getByRole('main')).toBeTruthy();
    expect(screen.getByRole('contentinfo')).toBeTruthy();
  });

  it('shows the same version as package.json', () => {
    expect(APP_VERSION).toBe(manifest.version);
  });
});
