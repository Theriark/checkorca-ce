/**
 * The "redirect" search parameter of /login: where to go after sign-in.
 *
 * Two gates. The router keeps only a same-origin path (one leading slash, no
 * protocol-relative "//host", no backslash, no control characters, no query
 * or fragment). The login page then goes there only when it is a known
 * section or plugin route; anything else lands on the morning check.
 */
import { isSectionPath } from './sections';

export const REDIRECT_PARAM = 'redirect';

/** A path the router accepts as a redirect candidate, or undefined. */
export function sanitiseRedirect(value: unknown): string | undefined {
  if (typeof value !== 'string' || value.length === 0 || value.length > 512) {
    return undefined;
  }
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return undefined;
  }
  if (/[\\\s?#]/.test(value)) {
    return undefined;
  }
  for (const character of value) {
    const code = character.charCodeAt(0);
    if (code < 0x20 || code === 0x7f) {
      return undefined;
    }
  }
  return value;
}

/** The address to open after sign-in: a known route, otherwise "/". */
export function resolveRedirect(candidate: string | undefined, pluginPaths: readonly string[] = []): string {
  if (!candidate) {
    return '/';
  }
  if (isSectionPath(candidate) || pluginPaths.includes(candidate)) {
    return candidate;
  }
  return '/';
}
