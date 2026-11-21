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
export const MESSAGES_PATH = '/messages';
export const MESSAGE_DETAIL_PATH = '/messages/$messageId';
/** A pack lives under /parsers/packs/<id>, so the bench at /parsers/bench
 *  can never collide with a pack id. */
export const PACK_DETAIL_PATH = '/parsers/packs/$packId';
export const BENCH_PATH = '/parsers/bench';

/** /clients/<id>: one path segment after /clients, nothing else. */
export function isClientDetailPath(pathname: string): boolean {
  return /^\/clients\/[^/]+$/.test(pathname);
}

/** /messages/<id>: one path segment after /messages, nothing else. */
export function isMessageDetailPath(pathname: string): boolean {
  return /^\/messages\/[^/]+$/.test(pathname);
}

/** /parsers/packs/<id>: one path segment after /parsers/packs, nothing else. */
export function isPackDetailPath(pathname: string): boolean {
  return /^\/parsers\/packs\/[^/]+$/.test(pathname);
}

export function isSectionPath(pathname: string): boolean {
  return (
    SECTIONS.some((section) => section.path === pathname) ||
    isClientDetailPath(pathname) ||
    pathname === MESSAGES_PATH ||
    isMessageDetailPath(pathname) ||
    isPackDetailPath(pathname) ||
    pathname === BENCH_PATH
  );
}
