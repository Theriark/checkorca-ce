import {
  Bell,
  Briefcase,
  Inbox,
  MailQuestion,
  Puzzle,
  Server,
  Settings,
  Sunrise,
  Users,
  type LucideIcon,
} from 'lucide-react';

import type { Role } from '../api/auth';
import { strings } from '../strings';

export type SectionKey =
  | 'morningCheck'
  | 'clients'
  | 'jobs'
  | 'unmatched'
  | 'inboxes'
  | 'parsers'
  | 'notifications'
  | 'system'
  | 'settings';

export interface NavItem {
  readonly key: SectionKey;
  readonly label: string;
  readonly to: string;
  readonly icon: LucideIcon;
  /** Roles that see it; every role when omitted. */
  readonly roles?: readonly Role[];
  /** Shown in the bottom bar at phone width. */
  readonly primary?: boolean;
  /** Other paths the item is current for (the messages under Inboxes). */
  readonly also?: readonly string[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { key: 'morningCheck', label: strings.nav.morningCheck, to: '/', icon: Sunrise, primary: true },
  { key: 'clients', label: strings.nav.clients, to: '/clients', icon: Users, primary: true },
  { key: 'jobs', label: strings.nav.jobs, to: '/jobs', icon: Briefcase, primary: true },
  { key: 'unmatched', label: strings.nav.unmatched, to: '/unmatched', icon: MailQuestion, primary: true },
  { key: 'inboxes', label: strings.nav.inboxes, to: '/inboxes', icon: Inbox, also: ['/messages'] },
  { key: 'parsers', label: strings.nav.parsers, to: '/parsers', icon: Puzzle },
  { key: 'notifications', label: strings.nav.notifications, to: '/notifications', icon: Bell },
  { key: 'system', label: strings.nav.system, to: '/system', icon: Server },
  { key: 'settings', label: strings.nav.settings, to: '/settings', icon: Settings, roles: ['admin'] },
];

export function navItemsFor(role: Role | null | undefined): readonly NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || (role !== null && role !== undefined && item.roles.includes(role)));
}
