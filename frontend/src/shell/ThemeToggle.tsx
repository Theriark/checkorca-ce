import { Moon, Sun } from 'lucide-react';

import { Button } from '../components/ui/Button';
import { strings } from '../strings';
import { useTheme } from '../theme/useTheme';

/** A toggle button named "Dark theme": pressed while the dark theme is in
 *  effect, with the icon of the theme it switches to. */
export function ThemeToggle({ withLabel = false }: { readonly withLabel?: boolean }) {
  const { theme, toggle } = useTheme();
  const dark = theme === 'dark';
  return (
    <Button
      variant="ghost"
      size="sm"
      iconOnly={!withLabel}
      iconStart={dark ? <Sun size={18} /> : <Moon size={18} />}
      onClick={toggle}
      aria-pressed={dark}
      data-theme-toggle={theme}
    >
      {strings.theme.dark}
    </Button>
  );
}
