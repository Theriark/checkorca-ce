import type { SectionKey } from '../shell/navigation';

/** The CE sections under the shell, path by path. Literal paths, so the
 *  router knows every section address and a Link to a typo fails to compile. */
export const SECTIONS = [
  { path: '/', key: 'morningCheck' },
  { path: '/clients', key: 'clients' },
  { path: '/jobs', key: 'jobs' },
  { path: '/unmatched', key: 'unmatched' },
  { path: '/inboxes', key: 'inboxes' },
  { path: '/parsers', key: 'parsers' },
  { path: '/notifications', key: 'notifications' },
  { path: '/system', key: 'system' },
  { path: '/settings', key: 'settings' },
] as const satisfies readonly { readonly path: string; readonly key: SectionKey }[];

export const CLIENT_DETAIL_PATH = '/clients/$clientId';

/** /clients/<id>: one path segment after /clients, nothing else. */
export function isClientDetailPath(pathname: string): boolean {
  return /^\/clients\/[^/]+$/.test(pathname);
}

export function isSectionPath(pathname: string): boolean {
  return SECTIONS.some((section) => section.path === pathname) || isClientDetailPath(pathname);
}
