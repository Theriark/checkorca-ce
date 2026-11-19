/** Date and time formatting for the UI: short, local, with the zone when it
 *  matters. Every function accepts the ISO strings the API sends. */

function parse(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function zoneIsKnown(timeZone: string): boolean {
  try {
    new Intl.DateTimeFormat(undefined, { timeZone });
    return true;
  } catch {
    return false;
  }
}

/** "Wed 19 Nov 2026, 23:00" in the browser's zone (or the given zone). */
export function formatDateTime(iso: string, timeZone?: string): string {
  const date = parse(iso);
  if (!date) {
    return iso;
  }
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  };
  if (timeZone && zoneIsKnown(timeZone)) {
    options.timeZone = timeZone;
  }
  return new Intl.DateTimeFormat('en-GB', options).format(date);
}

/** "19 Nov 2026". */
export function formatDate(iso: string): string {
  const date = parse(iso);
  if (!date) {
    return iso;
  }
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}

/** "23:00 UTC" for a time shown next to its local counterpart. */
export function formatUtcTime(iso: string): string {
  const date = parse(iso);
  if (!date) {
    return iso;
  }
  return `${new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }).format(date)} UTC`;
}

/** The value of a datetime-local input (local wall time) as an ISO instant. */
export function localInputToIso(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** The earliest value a datetime-local input accepts: now, in local time. */
export function nowForLocalInput(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** Replace {name} placeholders in a string from strings.ts. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));
}
