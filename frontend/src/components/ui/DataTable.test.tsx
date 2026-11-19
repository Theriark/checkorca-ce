import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import { strings } from '../../strings';
import { DataTable } from './DataTable';
import { readSavedViews, sortRows, type DataTableColumn } from './dataTableUtils';

interface Row {
  readonly id: string;
  readonly name: string;
  readonly runs: number | null;
}

const COLUMNS: readonly DataTableColumn<Row>[] = [
  { id: 'name', header: 'Name', cell: (row) => row.name, sortValue: (row) => row.name },
  { id: 'runs', header: 'Runs', cell: (row) => row.runs ?? '–', sortValue: (row) => row.runs, align: 'end', numeric: true },
];

const ROWS: readonly Row[] = [
  { id: 'b', name: 'Bravo', runs: 2 },
  { id: 'a', name: 'alpha', runs: 10 },
  { id: 'c', name: 'Charlie', runs: null },
];

function bodyNames(): string[] {
  const body = document.querySelector('tbody');
  return body ? Array.from(body.querySelectorAll('tr')).map((row) => row.querySelector('td')?.textContent ?? '') : [];
}

describe('sortRows', () => {
  it('sorts strings case-insensitively, numbers numerically, nulls last', () => {
    expect(sortRows(ROWS, COLUMNS[0], 'asc').map((row) => row.id)).toEqual(['a', 'b', 'c']);
    expect(sortRows(ROWS, COLUMNS[1], 'asc').map((row) => row.id)).toEqual(['b', 'a', 'c']);
    expect(sortRows(ROWS, COLUMNS[1], 'desc').map((row) => row.id)).toEqual(['c', 'a', 'b']);
    expect(sortRows(ROWS, undefined, 'asc')).toBe(ROWS);
  });
});

describe('DataTable', () => {
  it('renders rows with a sticky header and sorts by clicking a column', async () => {
    const user = userEvent.setup();
    render(<DataTable tableId="t1" caption="Jobs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />);
    expect(screen.getByRole('table', { name: 'Jobs' })).toBeTruthy();
    expect(document.querySelector('thead')?.className).toContain('co-table__head');
    expect(bodyNames()).toEqual(['Bravo', 'alpha', 'Charlie']);

    const header = screen.getByRole('columnheader', { name: /Name/ });
    await user.click(within(header).getByRole('button'));
    expect(header.getAttribute('aria-sort')).toBe('ascending');
    expect(bodyNames()).toEqual(['alpha', 'Bravo', 'Charlie']);

    await user.click(within(header).getByRole('button'));
    expect(header.getAttribute('aria-sort')).toBe('descending');
    expect(bodyNames()).toEqual(['Charlie', 'Bravo', 'alpha']);
  });

  it('switches density', async () => {
    const user = userEvent.setup();
    render(<DataTable tableId="t2" caption="Jobs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />);
    const group = screen.getByRole('group', { name: strings.table.density });
    const compact = within(group).getByRole('button', { name: strings.table.compact });
    expect(compact.getAttribute('aria-pressed')).toBe('false');
    await user.click(compact);
    expect(compact.getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelector('.co-table-wrap')?.className).toContain('co-table-wrap--compact');
  });

  it('saves the current sort and density as a named view in localStorage', async () => {
    const user = userEvent.setup();
    render(<DataTable tableId="t3" caption="Jobs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />);
    await user.click(within(screen.getByRole('columnheader', { name: /Runs/ })).getByRole('button'));
    await user.click(screen.getByRole('button', { name: strings.table.saveView }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(strings.table.viewName), 'Most runs');
    await user.click(within(dialog).getByRole('button', { name: strings.common.save }));
    const views = readSavedViews('t3');
    expect(views).toHaveLength(1);
    expect(views[0]).toMatchObject({ name: 'Most runs', sortColumn: 'runs', sortDirection: 'asc', density: 'comfortable' });
    expect(screen.getByRole('combobox', { name: strings.table.views }).textContent).toContain('Most runs');
  });

  it('refuses an empty view name', async () => {
    const user = userEvent.setup();
    render(<DataTable tableId="t4" caption="Jobs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />);
    await user.click(screen.getByRole('button', { name: strings.table.saveView }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: strings.common.save }));
    expect(within(dialog).getByRole('alert')).toBeTruthy();
    expect(readSavedViews('t4')).toEqual([]);
  });

  it('shows the loading, empty and error states', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(
      <DataTable tableId="t5" caption="Jobs" columns={COLUMNS} rows={[]} getRowId={(row) => row.id} loading skeletonRows={2} />,
    );
    expect(screen.getByRole('status').textContent).toContain(strings.states.loading);
    expect(document.querySelectorAll('.co-skeleton').length).toBeGreaterThan(0);

    rerender(
      <DataTable tableId="t5" caption="Jobs" columns={COLUMNS} rows={[]} getRowId={(row) => row.id} emptyTitle="No jobs yet" />,
    );
    expect(screen.getByRole('heading', { name: 'No jobs yet' })).toBeTruthy();

    rerender(
      <DataTable
        tableId="t5"
        caption="Jobs"
        columns={COLUMNS}
        rows={[]}
        getRowId={(row) => row.id}
        error={new ApiError({ title: 'Bad Gateway', status: 502, request_id: 'req-5' })}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole('alert').textContent).toContain('req-5');
    await user.click(screen.getByRole('button', { name: strings.states.retry }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
