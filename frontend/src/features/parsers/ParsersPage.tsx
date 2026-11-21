/**
 * /parsers: every parser pack with its vendor, version, source (built-in or
 * custom), the Unverified-synthetic or Verified badge, an enabled switch
 * (effective from the worker's next tick), import and export, and the test
 * bench. A row opens the pack. Technicians and admins see the same screen.
 */
import { Link, useNavigate } from '@tanstack/react-router';
import { Download, FlaskConical, Puzzle, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { PackOut } from '../../api/packs';
import { ActionMenu, type ActionItem } from '../../components/ui/ActionMenu';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Switch } from '../../components/ui/Switch';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { ImportPackDialog } from './ImportPackDialog';
import { PackSourceChip, PackStatusBadge } from './PackBadges';
import { exportPack } from './exportPack';
import { usePackList, useSetPackEnabled } from './queries';
import '../features.css';

export function ParsersPage() {
  const copy = strings.parsers;
  const { toast } = useToast();
  const navigate = useNavigate();
  const list = usePackList();
  const setEnabled = useSetPackEnabled();
  const [importOpen, setImportOpen] = useState(false);
  const packs = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);

  const open = (pack: PackOut) => void navigate({ to: '/parsers/packs/$packId', params: { packId: pack.id } });

  const toggle = (pack: PackOut, enabled: boolean) => {
    void setEnabled
      .mutateAsync({ packId: pack.id, enabled })
      .then(() => toast({ tone: 'success', title: enabled ? copy.enabledToast : copy.disabledToast, description: `${pack.id}. ${copy.toggleLead}` }))
      .catch((error: unknown) => toast({ tone: 'danger', title: enabled ? copy.enabledToast : copy.disabledToast, description: errorSentence(error) }));
  };

  const onExport = (pack: PackOut) => {
    void exportPack(pack.id)
      .then(() => toast({ tone: 'success', title: copy.exported, description: `${pack.id}.yaml` }))
      .catch((error: unknown) => toast({ tone: 'danger', title: copy.exportFailed, description: errorSentence(error) }));
  };

  const menuFor = (pack: PackOut): readonly ActionItem[] => [
    { id: 'open', label: copy.open, icon: <Puzzle size={16} />, onSelect: () => open(pack) },
    { id: 'export', label: copy.export, icon: <Download size={16} />, onSelect: () => onExport(pack) },
  ];

  const columns: DataTableColumn<PackOut>[] = [
    {
      id: 'pack',
      header: copy.columns.pack,
      sortValue: (pack) => pack.id,
      cell: (pack) => (
        <span className="co-cell-title">
          <Link to="/parsers/packs/$packId" params={{ packId: pack.id }} className="co-cell-title__name mono" onClick={(event) => event.stopPropagation()}>
            {pack.id}
          </Link>
          <span className="co-cell-title__sub">{pack.vendor}</span>
        </span>
      ),
    },
    { id: 'version', header: copy.columns.version, sortValue: (pack) => pack.version, numeric: true, cell: (pack) => <span className="tabular">{pack.version}</span> },
    { id: 'source', header: copy.columns.source, sortValue: (pack) => pack.source, cell: (pack) => <PackSourceChip source={pack.source} size="sm" /> },
    { id: 'status', header: copy.columns.status, sortValue: (pack) => pack.status, cell: (pack) => <PackStatusBadge status={pack.status} size="sm" /> },
    {
      id: 'enabled',
      header: copy.columns.enabled,
      sortValue: (pack) => (pack.enabled ? 1 : 0),
      cell: (pack) => (
        <span onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
          <Switch label={<span className="sr-only">{fill(copy.enabledFor, { name: pack.id })}</span>} checked={pack.enabled} onCheckedChange={(checked) => toggle(pack, checked)} disabled={setEnabled.isPending} />
        </span>
      ),
    },
    { id: 'updated', header: copy.columns.updated, sortValue: (pack) => pack.updated_at, numeric: true, cell: (pack) => formatDateTime(pack.updated_at) },
    {
      id: 'actions',
      header: <span className="sr-only">{copy.columns.actions}</span>,
      align: 'end',
      width: '56px',
      cell: (pack) => (
        <span className="co-cell-actions">
          <ActionMenu label={fill(copy.actionsFor, { name: pack.id })} items={menuFor(pack)} />
        </span>
      ),
    },
  ];

  const count = packs.length;
  const lead = list.isSuccess
    ? list.hasNextPage
      ? fill(copy.countMore, { count })
      : count === 1
        ? copy.countOne
        : fill(copy.count, { count })
    : copy.lead;

  return (
    <div className="co-page">
      <PageHeader
        icon={Puzzle}
        title={copy.title}
        lead={lead}
        actions={
          <>
            <Link to="/parsers/bench" className="co-button co-button--secondary co-button--md">
              <span className="co-button__icon" aria-hidden="true">
                <FlaskConical size={16} />
              </span>
              <span className="co-button__label">{copy.bench}</span>
            </Link>
            <Button variant="primary" iconStart={<Upload size={16} />} onClick={() => setImportOpen(true)}>
              {copy.import}
            </Button>
          </>
        }
      />

      <DataTable
        tableId="parsers"
        caption={copy.tableCaption}
        columns={columns}
        rows={packs}
        getRowId={(pack) => pack.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'pack', direction: 'asc' }}
        onRowClick={open}
        minWidth={820}
        emptyTitle={copy.emptyTitle}
        emptyDescription={copy.emptyLead}
        emptyAction={
          <Button variant="primary" iconStart={<Upload size={16} />} onClick={() => setImportOpen(true)}>
            {copy.import}
          </Button>
        }
      />
      {list.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}

      <ImportPackDialog open={importOpen} onOpenChange={setImportOpen} onImported={(pack) => void navigate({ to: '/parsers/packs/$packId', params: { packId: pack.id } })} />
    </div>
  );
}
