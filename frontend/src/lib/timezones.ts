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

/** Whether the zone is one this runtime can format: the same rule the
 *  server's IANA check follows, so UTC and the aliases pass here too (the
 *  suggestion list above is only a list, not the rule). */
export function isKnownTimeZone(zone: string): boolean {
  if (!zone.trim()) {
    return false;
  }
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}
