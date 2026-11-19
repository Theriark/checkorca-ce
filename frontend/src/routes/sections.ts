import type { SectionKey } from '../shell/navigation';

/** The CE sections under the shell, path by path. */
export const SECTIONS: readonly { readonly path: string; readonly key: SectionKey }[] = [
  { path: '/', key: 'morningCheck' },
  { path: '/clients', key: 'clients' },
  { path: '/jobs', key: 'jobs' },
  { path: '/unmatched', key: 'unmatched' },
  { path: '/inboxes', key: 'inboxes' },
  { path: '/parsers', key: 'parsers' },
  { path: '/notifications', key: 'notifications' },
  { path: '/system', key: 'system' },
  { path: '/settings', key: 'settings' },
];

export function isSectionPath(pathname: string): boolean {
  return SECTIONS.some((section) => section.path === pathname);
}
