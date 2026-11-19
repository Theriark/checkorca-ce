import { createContext } from 'react';

export type Theme = 'light' | 'dark';
export type ThemePreference = Theme | 'system';

export const THEME_STORAGE_KEY = 'checkorca.theme';

export interface ThemeContextValue {
  /** The theme in effect. */
  readonly theme: Theme;
  /** What the user chose; 'system' until they pick one. */
  readonly preference: ThemePreference;
  readonly setPreference: (preference: ThemePreference) => void;
  /** Light becomes dark and dark becomes light. */
  readonly toggle: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function resolveTheme(preference: ThemePreference, system: Theme): Theme {
  return preference === 'system' ? system : preference;
}

export function readStoredPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

export function readSystemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
