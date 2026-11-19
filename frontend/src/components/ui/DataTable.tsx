/**
 * DataTable: sticky header, density switch, click-to-sort columns and saved
 * views (sort plus density under a name, kept in localStorage per table).
 * Loading, empty and error states are designed, never a blank table.
 */
import { ArrowDown, ArrowUp, ArrowUpDown, Bookmark, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { strings } from '../../strings';
import { Button } from './Button';
import { Dialog } from './Dialog';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Input } from './Input';
import { Select } from './Select';
import { Skeleton } from './Skeleton';
import {
  DEFAULT_VIEW_ID,
  readSavedViews,
  sortRows,
  writeSavedViews,
  type DataTableColumn,
  type Density,
  type SavedView,
  type SortDirection,
} from './dataTableUtils';
import './ui.css';

export type { DataTableColumn, Density, SavedView, SortDirection } from './dataTableUtils';

export interface DataTableProps<Row> {
  /** Stable id: namespaces the saved views in localStorage. */
  readonly tableId: string;
  readonly caption: string;
  readonly columns: readonly DataTableColumn<Row>[];
  readonly rows: readonly Row[];
  readonly getRowId: (row: Row) => string;
  readonly loading?: boolean;
  readonly error?: unknown;
  readonly onRetry?: () => void;
  readonly emptyTitle?: ReactNode;
  readonly emptyDescription?: ReactNode;
  readonly emptyAction?: ReactNode;
  readonly defaultSort?: { readonly column: string; readonly direction: SortDirection };
  readonly defaultDensity?: Density;
  /** Content left of the density and views controls (search, filters). */
  readonly toolbar?: ReactNode;
  /** Rows the skeleton shows while loading. */
  readonly skeletonRows?: number;
  readonly onRowClick?: (row: Row) => void;
  /** The table's minimum width in pixels: below it the wrap scrolls
   *  sideways instead of squeezing the columns to one word per line. */
  readonly minWidth?: number;
  readonly className?: string;
}

export function DataTable<Row>({
  tableId,
  caption,
  columns,
  rows,
  getRowId,
  loading = false,
  error,
  onRetry,
  emptyTitle,
  emptyDescription,
  emptyAction,
  defaultSort,
  defaultDensity = 'comfortable',
  toolbar,
  skeletonRows = 6,
  onRowClick,
  minWidth,
  className,
}: DataTableProps<Row>) {
  const [sortColumn, setSortColumn] = useState<string | null>(defaultSort?.column ?? null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(defaultSort?.direction ?? 'asc');
  const [density, setDensity] = useState<Density>(defaultDensity);
  const [views, setViews] = useState<readonly SavedView[]>(() => readSavedViews(tableId));
  const [activeView, setActiveView] = useState<string>(DEFAULT_VIEW_ID);
  const [saveOpen, setSaveOpen] = useState(false);
  const [viewName, setViewName] = useState('');
  const [viewNameError, setViewNameError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    writeSavedViews(tableId, views);
  }, [tableId, views]);

  const column = columns.find((item) => item.id === sortColumn);
  const sorted = useMemo(() => sortRows(rows, column, sortDirection), [rows, column, sortDirection]);

  const toggleSort = useCallback(
    (id: string) => {
      setActiveView(DEFAULT_VIEW_ID);
      if (sortColumn !== id) {
        setSortColumn(id);
        setSortDirection('asc');
        return;
      }
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    },
    [sortColumn],
  );

  const applyView = useCallback(
    (id: string) => {
      setActiveView(id);
      if (id === DEFAULT_VIEW_ID) {
        setSortColumn(defaultSort?.column ?? null);
        setSortDirection(defaultSort?.direction ?? 'asc');
        setDensity(defaultDensity);
        return;
      }
      const view = views.find((item) => item.id === id);
      if (view) {
        setSortColumn(view.sortColumn);
        setSortDirection(view.sortDirection);
        setDensity(view.density);
      }
    },
    [defaultDensity, defaultSort, views],
  );

  const saveView = useCallback(() => {
    const name = viewName.trim();
    if (!name) {
      setViewNameError(strings.table.viewName);
      return;
    }
    const id = `${Date.now()}`;
    setViews((current) => [...current, { id, name, sortColumn, sortDirection, density }]);
    setActiveView(id);
    setViewName('');
    setViewNameError(null);
    setSaveOpen(false);
  }, [density, sortColumn, sortDirection, viewName]);

  const deleteView = useCallback(() => {
    setViews((current) => current.filter((item) => item.id !== activeView));
    applyView(DEFAULT_VIEW_ID);
  }, [activeView, applyView]);

  const viewOptions = [
    { value: DEFAULT_VIEW_ID, label: strings.table.defaultView },
    ...views.map((view) => ({ value: view.id, label: view.name })),
  ];

  const classes = ['co-table-wrap', `co-table-wrap--${density}`];
  if (className) {
    classes.push(className);
  }

  const hasRows = sorted.length > 0;
  const showBody = !loading && !error && hasRows;

  return (
    <div className={classes.join(' ')}>
      <div className="co-table__toolbar">
        <div className="co-table__toolbar-start">{toolbar}</div>
        <div className="co-table__toolbar-end">
          <Select
            label={strings.table.views}
            hideLabel
            size="sm"
            options={viewOptions}
            value={activeView}
            onValueChange={applyView}
          />
          {activeView !== DEFAULT_VIEW_ID && (
            <Button size="sm" variant="ghost" iconOnly iconStart={<Trash2 size={16} />} onClick={deleteView}>
              {strings.table.deleteView}
            </Button>
          )}
          <Button size="sm" variant="secondary" iconStart={<Bookmark size={16} />} onClick={() => setSaveOpen(true)}>
            {strings.table.saveView}
          </Button>
          <div className="co-segmented" role="group" aria-label={strings.table.density}>
            <button
              type="button"
              className="co-segmented__option"
              aria-pressed={density === 'comfortable'}
              onClick={() => setDensity('comfortable')}
            >
              {strings.table.comfortable}
            </button>
            <button
              type="button"
              className="co-segmented__option"
              aria-pressed={density === 'compact'}
              onClick={() => setDensity('compact')}
            >
              {strings.table.compact}
            </button>
          </div>
        </div>
      </div>

      <div className="co-table__scroll">
        <table className="co-table" style={minWidth ? { minWidth } : undefined}>
          <caption className="sr-only">{caption}</caption>
          <thead className="co-table__head">
            <tr>
              {columns.map((item) => {
                const sortable = Boolean(item.sortValue);
                const active = sortColumn === item.id;
                const ariaSort = active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : undefined;
                const SortIcon = active ? (sortDirection === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
                return (
                  <th
                    key={item.id}
                    scope="col"
                    className={`co-table__th${item.align === 'end' ? ' co-table__th--end' : ''}`}
                    style={item.width ? { width: item.width } : undefined}
                    aria-sort={ariaSort}
                  >
                    {sortable ? (
                      <button type="button" className="co-table__sort" onClick={() => toggleSort(item.id)}>
                        <span>{item.header}</span>
                        <SortIcon className="co-table__sort-icon" size={14} aria-hidden="true" />
                        <span className="sr-only">
                          , {strings.table.sortBy}
                          {active ? `, ${sortDirection === 'asc' ? strings.table.sortedAscending : strings.table.sortedDescending}` : ''}
                        </span>
                      </button>
                    ) : (
                      item.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          {showBody && (
            <tbody>
              {sorted.map((row) => (
                <tr
                  key={getRowId(row)}
                  className={onRowClick ? 'co-table__row co-table__row--clickable' : 'co-table__row'}
                  // A clickable row is also reachable by keyboard: Tab to it,
                  // Enter or Space opens it. Keys pressed inside a cell control
                  // (a button or link in the row) are left to that control.
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                            event.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((item) => (
                    <td
                      key={item.id}
                      className={`co-table__td${item.align === 'end' ? ' co-table__td--end' : ''}${item.numeric ? ' tabular' : ''}`}
                    >
                      {item.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          )}
          {loading && (
            <tbody aria-busy="true">
              {Array.from({ length: skeletonRows }, (_, rowIndex) => (
                <tr key={rowIndex} className="co-table__row">
                  {columns.map((item, columnIndex) => (
                    <td key={item.id} className="co-table__td">
                      <Skeleton height={12} width={columnIndex === 0 ? '70%' : '45%'} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          )}
        </table>
        {loading && (
          <p className="sr-only" role="status">
            {strings.states.loading}
          </p>
        )}
      </div>

      {!loading && error !== undefined && error !== null && (
        <div className="co-table__state">
          <ErrorState error={error} onRetry={onRetry} compact />
        </div>
      )}
      {!loading && !error && !hasRows && (
        <div className="co-table__state">
          <EmptyState
            compact
            title={emptyTitle ?? strings.table.emptyTitle}
            description={emptyDescription ?? strings.table.emptyLead}
            action={emptyAction}
          />
        </div>
      )}

      <Dialog
        open={saveOpen}
        onOpenChange={(open) => {
          setSaveOpen(open);
          if (!open) {
            setViewNameError(null);
          }
        }}
        title={strings.table.saveView}
        description={strings.table.saveViewLead}
        size="sm"
        initialFocusRef={nameRef}
        footer={
          <>
            <Button variant="ghost" onClick={() => setSaveOpen(false)}>
              {strings.common.cancel}
            </Button>
            <Button variant="primary" onClick={saveView}>
              {strings.common.save}
            </Button>
          </>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            saveView();
          }}
        >
          <Input
            ref={nameRef}
            label={strings.table.viewName}
            value={viewName}
            onChange={(event) => setViewName(event.target.value)}
            error={viewNameError}
            maxLength={40}
          />
        </form>
      </Dialog>
    </div>
  );
}
