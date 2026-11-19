import type { ReactNode } from 'react';

export type SortDirection = 'asc' | 'desc';
export type Density = 'comfortable' | 'compact';

export interface DataTableColumn<Row> {
  readonly id: string;
  readonly header: ReactNode;
  readonly cell: (row: Row) => ReactNode;
  /** The value to sort by; omit for an unsortable column. */
  readonly sortValue?: (row: Row) => string | number | null | undefined;
  readonly align?: 'start' | 'end';
  readonly width?: string;
  /** Tabular figures (numbers and times). */
  readonly numeric?: boolean;
}

export interface SavedView {
  readonly id: string;
  readonly name: string;
  readonly sortColumn: string | null;
  readonly sortDirection: SortDirection;
  readonly density: Density;
}

export const DEFAULT_VIEW_ID = 'default';

function storageKey(tableId: string): string {
  return `checkorca.table.${tableId}.views`;
}

/** localStorage is user-writable: only a well-formed entry is a saved view. */
function isSavedView(value: unknown): value is SavedView {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.id === 'string' &&
    typeof entry.name === 'string' &&
    entry.name.length > 0 &&
    (entry.sortColumn === null || typeof entry.sortColumn === 'string') &&
    (entry.sortDirection === 'asc' || entry.sortDirection === 'desc') &&
    (entry.density === 'comfortable' || entry.density === 'compact')
  );
}

export function readSavedViews(tableId: string): readonly SavedView[] {
  try {
    const raw = window.localStorage.getItem(storageKey(tableId));
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isSavedView) : [];
  } catch {
    return [];
  }
}

export function writeSavedViews(tableId: string, views: readonly SavedView[]): void {
  try {
    window.localStorage.setItem(storageKey(tableId), JSON.stringify(views));
  } catch {
    // Storage unavailable: the view lasts for this page only.
  }
}

function compare(a: string | number | null | undefined, b: string | number | null | undefined): number {
  if (a === b) {
    return 0;
  }
  if (a === null || a === undefined) {
    return 1;
  }
  if (b === null || b === undefined) {
    return -1;
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

export function sortRows<Row>(
  rows: readonly Row[],
  column: DataTableColumn<Row> | undefined,
  direction: SortDirection,
): readonly Row[] {
  if (!column?.sortValue) {
    return rows;
  }
  const getter = column.sortValue;
  const sorted = [...rows].sort((a, b) => compare(getter(a), getter(b)));
  return direction === 'asc' ? sorted : sorted.reverse();
}
