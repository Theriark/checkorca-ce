import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useNavigate } from '@tanstack/react-router';
import { ChevronDown, LogOut, UserRound } from 'lucide-react';
import { useState } from 'react';

import type { Me } from '../api/auth';
import { useAuth } from '../auth/useAuth';
import { useToast } from '../components/ui/useToast';
import { strings } from '../strings';
import { ThemeToggle } from './ThemeToggle';
import { initialsOf } from './initials';
import './shell.css';

export function UserMenu({ user }: { readonly user: Me }) {
  const { signOut } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const onSignOut = async () => {
    setBusy(true);
    try {
      await signOut();
      await navigate({ to: '/login' });
    } catch (error) {
      toast({ tone: 'danger', title: strings.user.signOutFailed, description: error instanceof Error ? error.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="co-usermenu__trigger">
          <span className="sr-only">{strings.user.menu}: </span>
          <span className="co-usermenu__avatar" aria-hidden="true">
            {initialsOf(user.email)}
          </span>
          <span className="co-usermenu__text">
            <span className="co-usermenu__email">{user.email}</span>
            <span className="co-usermenu__role">{strings.user.role[user.role]}</span>
          </span>
          <ChevronDown className="co-usermenu__chevron" size={16} aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="co-menu" align="end" sideOffset={6}>
          <DropdownMenu.Label className="co-menu__label">
            <span className="caps">{strings.user.signedInAs}</span>
            <span className="co-menu__email">{user.email}</span>
            <span className="co-menu__role">
              <UserRound size={14} aria-hidden="true" /> {strings.user.role[user.role]}
            </span>
          </DropdownMenu.Label>
          <DropdownMenu.Separator className="co-menu__separator" />
          <div className="co-menu__row">
            <ThemeToggle withLabel />
          </div>
          <DropdownMenu.Separator className="co-menu__separator" />
          <DropdownMenu.Item className="co-menu__item" disabled={busy} onSelect={() => void onSignOut()}>
            <LogOut size={16} aria-hidden="true" />
            {busy ? strings.user.signingOut : strings.user.signOut}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
