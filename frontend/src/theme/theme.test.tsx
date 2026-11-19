import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ThemeProvider } from './ThemeProvider';
import { THEME_STORAGE_KEY, resolveTheme } from './context';
import { useTheme } from './useTheme';

function Probe() {
  const { theme, preference, toggle, setPreference } = useTheme();
  return (
    <div>
      <output data-testid="theme">{theme}</output>
      <output data-testid="preference">{preference}</output>
      <button onClick={toggle}>toggle</button>
      <button onClick={() => setPreference('system')}>system</button>
    </div>
  );
}

describe('theme', () => {
  it('resolves the system preference', () => {
    expect(resolveTheme('system', 'dark')).toBe('dark');
    expect(resolveTheme('light', 'dark')).toBe('light');
    expect(resolveTheme('dark', 'light')).toBe('dark');
  });

  it('follows the system until the user toggles, then stores the choice as data-theme', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('preference').textContent).toBe('system');
    expect(screen.getByTestId('theme').textContent).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();

    await user.click(screen.getByText('toggle'));
    expect(screen.getByTestId('theme').textContent).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await user.click(screen.getByText('toggle'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    await user.click(screen.getByText('system'));
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('reads a stored preference on start', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    act(() => {
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );
    });
    expect(screen.getByTestId('theme').textContent).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
