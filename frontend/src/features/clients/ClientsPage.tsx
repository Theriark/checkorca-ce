/**
 * /clients: every client with its job count and worst state; search, a
 * status filter, the archived toggle and the create dialog. A row opens the
 * client.
 */
import { Link, useNavigate } from '@tanstack/react-router';
import { Plus, Users } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { ClientOut } from '../../api/clients';
import { JOB_STATES, type JobState } from '../../api/jobs';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import { Switch } from '../../components/ui/Switch';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { fill, formatDate } from '../../lib/format';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { strings } from '../../strings';
import { STATE_SEVERITY, stateLabel } from '../jobs/jobState';
import { PageHeader } from '../shared/PageHeader';
import { ClientDialog } from './ClientDialog';
import { useClientList } from './queries';
import '../features.css';

const ALL = 'all';

export function ClientsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>(ALL);
  const [archived, setArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const q = useDebouncedValue(search.trim(), 300);
  const list = useClientList({ q, archived });

  const clients = useMemo(() => {
    const items = list.data?.pages.flatMap((page) => page.items) ?? [];
    // The status filter is applied to the loaded rows: the API lists by name.
    return status === ALL ? items : items.filter((client) => client.worst_state === status);
  }, [list.data, status]);
  const filtered = q.length > 0 || status !== ALL;

  const open = (client: ClientOut) => void navigate({ to: '/clients/$clientId', params: { clientId: client.id } });

  const columns: DataTableColumn<ClientOut>[] = [
    {
      id: 'name',
      header: strings.clients.columns.name,
      sortValue: (client) => client.name,
      cell: (client) => (
        <span className="co-cell-title">
          <Link to="/clients/$clientId" params={{ clientId: client.id }} className="co-cell-title__name" onClick={(event) => event.stopPropagation()}>
            {client.name}
          </Link>
          {client.aliases.length > 0 && <span className="co-cell-title__sub">{client.aliases.join(', ')}</span>}
        </span>
      ),
    },
    {
      id: 'jobs',
      header: strings.clients.columns.jobs,
      sortValue: (client) => client.job_count,
      align: 'end',
      numeric: true,
      cell: (client) => client.job_count,
    },
    {
      id: 'status',
      header: strings.clients.columns.status,
      sortValue: (client) => client.worst_state ?? '',
      cell: (client) => (
        <span className="co-cell-state">
          {client.worst_state ? <SeverityBadge severity={STATE_SEVERITY[client.worst_state]} size="sm" /> : <span className="co-cell-muted">{strings.clients.noJobs}</span>}
          {client.archived && <span className="co-chip">{strings.clients.archived}</span>}
        </span>
      ),
    },
    {
      id: 'notes',
      header: strings.clients.columns.notes,
      cell: (client) => (client.notes ? <span className="co-cell-notes">{client.notes}</span> : null),
    },
    {
      id: 'created',
      header: strings.clients.columns.created,
      sortValue: (client) => client.created_at,
      numeric: true,
      cell: (client) => formatDate(client.created_at),
    },
  ];

  const count = clients.length;
  const lead = list.isSuccess ? (count === 1 ? strings.clients.countOne : fill(strings.clients.count, { count })) : strings.clients.lead;

  return (
    <div className="co-page">
      <PageHeader
        icon={Users}
        title={strings.clients.title}
        lead={lead}
        actions={
          <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            {strings.clients.new}
          </Button>
        }
      />

      <DataTable
        tableId="clients"
        caption={strings.clients.tableCaption}
        columns={columns}
        rows={clients}
        getRowId={(client) => client.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'name', direction: 'asc' }}
        onRowClick={open}
        minWidth={720}
        emptyTitle={archived ? strings.clients.emptyArchived : filtered ? strings.clients.noMatch : strings.clients.emptyTitle}
        emptyDescription={archived ? strings.clients.emptyArchivedLead : filtered ? strings.clients.noMatchLead : strings.clients.emptyLead}
        emptyAction={
          !archived && !filtered ? (
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
              {strings.clients.new}
            </Button>
          ) : undefined
        }
        toolbar={
          <div className="co-filters">
            <Input
              className="co-filters__search"
              label={<span className="sr-only">{strings.clients.search}</span>}
              type="search"
              placeholder={strings.clients.searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Select
              className="co-filters__select"
              label={strings.clients.status}
              hideLabel
              size="sm"
              value={status}
              onValueChange={setStatus}
              options={[{ value: ALL, label: strings.clients.anyStatus }, ...JOB_STATES.map((state: JobState) => ({ value: state, label: stateLabel(state) }))]}
            />
            <Switch className="co-filters__switch" label={strings.clients.showArchived} checked={archived} onCheckedChange={setArchived} />
          </div>
        }
      />
      {list.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}

      <ClientDialog open={createOpen} onOpenChange={setCreateOpen} client={null} onSaved={open} />
    </div>
  );
}
