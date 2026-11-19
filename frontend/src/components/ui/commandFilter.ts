import type { CommandItem } from './CommandSearch';

/** Items whose label or keywords contain the query (case-insensitive). */
export function filterCommands(items: readonly CommandItem[], query: string): readonly CommandItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return items;
  }
  return items.filter(
    (item) =>
      item.label.toLowerCase().includes(needle) ||
      (item.keywords ?? []).some((keyword) => keyword.toLowerCase().includes(needle)),
  );
}
