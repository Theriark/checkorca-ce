import type { SectionKey } from '../shell/navigation';

/** The CE sections under the shell, path by path. Literal paths, so the
 *  router knows every section address and a Link to a typo fails to compile.
 *  /notifications has its own route (it keeps its tab and filters in the
 *  address), so it is not in this list. */
export const SECTIONS = [
  { path: '/', key: 'morningCheck' },
  { path: '/clients', key: 'clients' },
  { path: '/jobs', key: 'jobs' },
  { path: '/unmatched', key: 'unmatched' },
  { path: '/inboxes', key: 'inboxes' },
  { path: '/parsers', key: 'parsers' },
  { path: '/system', key: 'system' },
  { path: '/settings', key: 'settings' },
] as const satisfies readonly { readonly path: string; readonly key: SectionKey }[];

export const NOTIFICATIONS_PATH = '/notifications';
export const CLIENT_DETAIL_PATH = '/clients/$clientId';
export const JOB_DETAIL_PATH = '/jobs/$jobId';
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

/** /jobs/<id>: one path segment after /jobs, nothing else. */
export function isJobDetailPath(pathname: string): boolean {
  return /^\/jobs\/[^/]+$/.test(pathname);
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
    pathname === NOTIFICATIONS_PATH ||
    isClientDetailPath(pathname) ||
    isJobDetailPath(pathname) ||
    pathname === MESSAGES_PATH ||
    isMessageDetailPath(pathname) ||
    isPackDetailPath(pathname) ||
    pathname === BENCH_PATH
  );
}
