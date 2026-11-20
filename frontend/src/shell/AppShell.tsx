/**
 * The signed-in frame: header (logo, command search, theme, account), the
 * section sidebar (full from 1024 px, an icon rail from 640 px) and the bottom
 * bar under 640 px with the four primary sections and a "More" sheet.
 */
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router';
import { LayoutGrid, LogOut, Mail, Moon, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { Me } from '../api/auth';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/ui/Button';
import { CommandSearch, type CommandItem } from '../components/ui/CommandSearch';
import { Dialog } from '../components/ui/Dialog';
import { useToast } from '../components/ui/useToast';
import { usePluginSlot } from '../plugins/slots';
import { APP_VERSION, PRODUCT_NAME, strings } from '../strings';
import { useTheme } from '../theme/useTheme';
import { Logo } from './Logo';
import { StaleWorkerBanner } from './StaleWorkerBanner';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';
import { navItemsFor, type NavItem } from './navigation';
import './shell.css';

function matches(pathname: string, to: string): boolean {
  return to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`);
}

function isActive(pathname: string, item: LinkItem): boolean {
  return matches(pathname, item.to) || (item.also ?? []).some((path) => matches(pathname, path));
}

type LinkItem = Pick<NavItem, 'to' | 'label' | 'icon' | 'also'>;

function SectionLink({ item, pathname, onNavigate, rail = false }: {
  readonly item: LinkItem;
  readonly pathname: string;
  readonly onNavigate?: () => void;
  readonly rail?: boolean;
}) {
  const active = isActive(pathname, item);
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      className={rail ? 'co-nav__link co-nav__link--rail' : 'co-nav__link'}
      aria-current={active ? 'page' : undefined}
      onClick={onNavigate}
    >
      <Icon className="co-nav__icon" size={20} aria-hidden="true" strokeWidth={active ? 2.25 : 1.75} />
      <span className="co-nav__label">{item.label}</span>
    </Link>
  );
}

export function AppShell({ user }: { readonly user: Me }) {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const { toggle, theme } = useTheme();
  const { signOut } = useAuth();
  const { toast } = useToast();
  const pluginMenu = usePluginSlot('menu');
  const [searchOpen, setSearchOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  // Sign out from the command search or the More sheet: a failed logout keeps
  // the session (AuthProvider) and is reported, never swallowed.
  const onSignOut = useCallback(async () => {
    try {
      await signOut();
      await navigate({ to: '/login' });
    } catch (error) {
      toast({ tone: 'danger', title: strings.user.signOutFailed, description: error instanceof Error ? error.message : undefined });
    }
  }, [navigate, signOut, toast]);

  const items = navItemsFor(user.role);
  const primary = items.filter((item) => item.primary);
  const secondary = items.filter((item) => !item.primary);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const closeMore = useCallback(() => setMoreOpen(false), []);

  const commands = useMemo<readonly CommandItem[]>(() => {
    const sections: CommandItem[] = [...items, ...pluginMenu].map((item) => {
      const Icon = item.icon;
      return {
        id: `section-${item.to}`,
        label: item.label,
        group: 'sections',
        icon: <Icon size={16} />,
        keywords: [item.to],
        run: () => void navigate({ to: item.to }),
      };
    });
    sections.push({
      id: 'section-/messages',
      label: strings.messages.title,
      group: 'sections',
      icon: <Mail size={16} />,
      keywords: ['/messages', 'mail'],
      run: () => void navigate({ to: '/messages' }),
    });
    const actions: CommandItem[] = [
      {
        id: 'action-theme',
        label: theme === 'dark' ? strings.theme.switchToLight : strings.theme.switchToDark,
        group: 'actions',
        icon: <Moon size={16} />,
        keywords: ['theme', 'dark', 'light'],
        run: toggle,
      },
      {
        id: 'action-sign-out',
        label: strings.user.signOut,
        group: 'actions',
        icon: <LogOut size={16} />,
        keywords: ['logout'],
        run: () => void onSignOut(),
      },
    ];
    return [...sections, ...actions];
  }, [items, navigate, onSignOut, pluginMenu, theme, toggle]);

  return (
    <div className="co-shell">
      <a className="co-shell__skip" href="#main">
        {strings.nav.skipToContent}
      </a>
      <header className="co-shell__header">
        <Link to="/" className="co-shell__brand" aria-label={`${PRODUCT_NAME}: ${strings.nav.morningCheck}`}>
          <Logo variant="horizontal" width={180} className="co-shell__logo" />
        </Link>
        <div className="co-shell__header-end">
          <button type="button" className="co-shell__search" onClick={() => setSearchOpen(true)}>
            <Search size={16} aria-hidden="true" />
            <span className="co-shell__search-label">{strings.search.open}</span>
            <kbd className="co-shell__search-kbd" aria-hidden="true">
              {strings.search.shortcut}
            </kbd>
          </button>
          <ThemeToggle />
          <UserMenu user={user} />
        </div>
      </header>

      <nav className="co-shell__sidebar" aria-label={strings.nav.primary}>
        <ul className="co-nav">
          {items.map((item) => (
            <li key={item.key}>
              <SectionLink item={item} pathname={pathname} rail />
            </li>
          ))}
          {pluginMenu.map((item) => (
            <li key={item.to}>
              <SectionLink item={item} pathname={pathname} rail />
            </li>
          ))}
        </ul>
        <div className="co-shell__sidebar-foot">
          <span className="co-shell__edition">{strings.edition}</span>
          <span className="co-shell__version tabular">{APP_VERSION}</span>
        </div>
      </nav>

      <main id="main" className="co-shell__main" tabIndex={-1}>
        <StaleWorkerBanner />
        <Outlet />
      </main>

      <nav className="co-shell__bottom" aria-label={strings.nav.quick}>
        <ul className="co-bottom">
          {primary.map((item) => (
            <li key={item.key}>
              <SectionLink item={item} pathname={pathname} />
            </li>
          ))}
          <li>
            <button
              type="button"
              className="co-nav__link co-nav__link--button"
              aria-haspopup="dialog"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen(true)}
            >
              <LayoutGrid className="co-nav__icon" size={20} aria-hidden="true" strokeWidth={1.75} />
              <span className="co-nav__label">{strings.nav.more}</span>
            </button>
          </li>
        </ul>
      </nav>

      <Dialog open={moreOpen} onOpenChange={setMoreOpen} title={strings.nav.sections} description={strings.tagline} size="sm">
        <ul className="co-nav co-nav--sheet">
          {[...secondary, ...pluginMenu].map((item) => (
            <li key={item.to}>
              <SectionLink item={item} pathname={pathname} onNavigate={closeMore} />
            </li>
          ))}
        </ul>
        <div className="co-sheet__foot">
          <ThemeToggle withLabel />
          <Button
            variant="ghost"
            size="sm"
            iconStart={<LogOut size={16} />}
            onClick={() => {
              closeMore();
              void onSignOut();
            }}
          >
            {strings.user.signOut}
          </Button>
        </div>
      </Dialog>

      <CommandSearch items={commands} open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
