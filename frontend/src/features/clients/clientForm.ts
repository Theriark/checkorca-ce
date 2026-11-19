/** Limits and parsing of the client form (NewClient in docs/openapi.json). */
export const MAX_NAME_LENGTH = 200;
export const MAX_NOTES_LENGTH = 4000;

/** One alias per line, trimmed, empty lines dropped. */
export function parseAliases(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

/** The server compares after collapsing runs of spaces; so does the button. */
export function namesMatch(typed: string, name: string): boolean {
  return typed.trim().split(/\s+/).join(' ') === name;
}
