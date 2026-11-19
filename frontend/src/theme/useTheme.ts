import { useContext } from 'react';

import { ThemeContext, type ThemeContextValue } from './context';

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error('useTheme needs a ThemeProvider above it');
  }
  return value;
}
