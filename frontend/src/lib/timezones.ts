/** IANA time zones the browser knows, for the zone field's suggestions. */

const FALLBACK: readonly string[] = ['UTC', 'Europe/Lisbon', 'Europe/London', 'Europe/Madrid', 'Europe/Berlin', 'America/New_York'];

export function knownTimeZones(): readonly string[] {
  try {
    const zones = Intl.supportedValuesOf('timeZone');
    return zones.length > 0 ? zones : FALLBACK;
  } catch {
    return FALLBACK;
  }
}

/** The browser's zone, the natural default for a new job. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}
