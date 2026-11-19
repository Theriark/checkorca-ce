/**
 * Theme: light or dark, following the system until the user chooses.
 *
 * The choice is stored in localStorage and written as data-theme on the html
 * element so tokens.css switches without a flash on the next load: the CSS
 * follows prefers-color-scheme when no attribute is set.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  THEME_STORAGE_KEY,
  ThemeContext,
  readStoredPreference,
  readSystemTheme,
  resolveTheme,
  type Theme,
  type ThemeContextValue,
  type ThemePreference,
} from './context';

export function ThemeProvider({ children }: { readonly children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference);
  const [system, setSystem] = useState<Theme>(readSystemTheme);

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!media) {
      return undefined;
    }
    const onChange = (event: MediaQueryListEvent) => setSystem(event.matches ? 'dark' : 'light');
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const theme = resolveTheme(preference, system);

  useEffect(() => {
    const root = document.documentElement;
    if (preference === 'system') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', preference);
    }
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    try {
      if (next === 'system') {
        window.localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        window.localStorage.setItem(THEME_STORAGE_KEY, next);
      }
    } catch {
      // Private mode or a full store: the choice lasts for this page only.
    }
  }, []);

  const toggle = useCallback(() => {
    setPreference(theme === 'dark' ? 'light' : 'dark');
  }, [setPreference, theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, preference, setPreference, toggle }),
    [theme, preference, setPreference, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
