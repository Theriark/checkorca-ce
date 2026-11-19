/**
 * /clients/:id: the client's summary, its jobs (with the job editor, pause,
 * resume and archive), the plugin tab slot (empty in CE), edit, archive or
 * restore, and the delete dialog that asks for the typed name.
 */
import { Link, useNavigate, useParams } from '@tanstack/react-router';
import { Archive, ArchiveRestore, ArrowLeft, Download, Pencil, Plus, Trash2, Users } from 'lucide-react';
import { useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import type { ClientOut } from '../../api/clients';
import type { JobOut, JobState } from '../../api/jobs';
import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { Switch } from '../../components/ui/Switch';
import { Tabs, type TabItem } from '../../components/ui/Tabs';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDate } from '../../lib/format';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { usePluginSlot } from '../../plugins/slots';
import { strings } from '../../strings';
import { JobDrawer } from '../jobs/JobDrawer';
import { JobsTable } from '../jobs/JobsTable';
import { exportJobs } from '../jobs/exportJobs';
import { STATE_SEVERITY, stateLabel } from '../jobs/jobState';
import { useJobList } from '../jobs/queries';
import { useJobActions } from '../jobs/useJobActions';
import { JOB_STATES } from '../../api/jobs';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { ClientDialog } from './ClientDialog';
import { DeleteClientDialog } from './DeleteClientDialog';
import { useArchiveClient, useClient, useUpdateClient } from './queries';
import '../features.css';

const ALL = 'all';
const JOBS_TAB = 'jobs';

function Summary({ client }: { readonly client: ClientOut }) {
  const states = JOB_STATES.filter((state) => (client.status_counts[state] ?? 0) > 0);
  return (
    <section className="co-card" aria-labelledby="client-summary-title">
      <h2 id="client-summary-title" className="co-card__title">
        {strings.clients.detail.summary}
      </h2>
      <div className="co-summary">
        <dl className="co-kv">
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.detail.jobCount}</dt>
            <dd className="co-kv__value co-kv__value--big tabular">{client.job_count}</dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.detail.worstState}</dt>
            <dd className="co-kv__value">
              {client.worst_state ? <SeverityBadge severity={STATE_SEVERITY[client.worst_state]} /> : <span className="co-summary__muted">{strings.clients.noJobs}</span>}
            </dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.detail.statusCounts}</dt>
            <dd className="co-kv__value">
              {states.length === 0 ? (
                <span className="co-summary__muted">{strings.common.none}</span>
              ) : (
                <span className="co-summary__counts">
                  {states.map((state) => (
                    <SeverityBadge key={state} severity={STATE_SEVERITY[state]} size="sm" detail={String(client.status_counts[state])} />
                  ))}
                </span>
              )}
            </dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.detail.createdOn}</dt>
            <dd className="co-kv__value tabular">{formatDate(client.created_at)}</dd>
          </div>
        </dl>
        <dl className="co-kv">
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.aliases}</dt>
            <dd className="co-kv__value">
              {client.aliases.length === 0 ? (
                <span className="co-summary__muted">{strings.clients.detail.aliasesEmpty}</span>
              ) : (
                <ul className="co-chips">
                  {client.aliases.map((alias) => (
                    <li key={alias} className="co-chip">
                      {alias}
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.clients.form.notes}</dt>
            <dd className="co-kv__value co-summary__notes">{client.notes ? client.notes : <span className="co-summary__muted">{strings.clients.detail.notesEmpty}</span>}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function ClientJobs({ client, onNew, actions, onEdit }: { readonly client: ClientOut; readonly onNew: () => void; readonly actions: ReturnType<typeof useJobActions>; readonly onEdit: (job: JobOut) => void }) {
  const [search, setSearch] = useState('');
  const [state, setState] = useState<string>(ALL);
  const [archived, setArchived] = useState(false);
  const q = useDebouncedValue(search.trim(), 300);
  const filters = useMemo(() => ({ client_id: client.id, q, state: state === ALL ? null : (state as JobState), archived }), [client.id, q, state, archived]);
  const list = useJobList(filters);
  const jobs = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const filtered = q.length > 0 || state !== ALL;
  return (
    <>
      <JobsTable
        tableId={`client-jobs`}
        jobs={jobs}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        showClient={false}
        onEdit={onEdit}
        actions={actions}
        emptyTitle={archived ? strings.jobs.emptyArchived : filtered ? strings.jobs.noMatch : strings.clients.detail.noJobsTitle}
        emptyDescription={filtered ? strings.jobs.noMatchLead : archived ? undefined : strings.clients.detail.noJobsLead}
        emptyAction={
          !filtered && !archived && !client.archived ? (
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={onNew}>
              {strings.clients.detail.newJob}
            </Button>
          ) : undefined
        }
        toolbar={
          <div className="co-filters">
            <Input
              className="co-filters__search"
              label={<span className="sr-only">{strings.jobs.search}</span>}
              type="search"
              placeholder={strings.jobs.searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Select
              className="co-filters__select"
              label={strings.jobs.state}
              hideLabel
              size="sm"
              value={state}
              onValueChange={setState}
              options={[{ value: ALL, label: strings.jobs.anyState }, ...JOB_STATES.map((item) => ({ value: item, label: stateLabel(item) }))]}
            />
            <Switch className="co-filters__switch" label={strings.jobs.showArchived} checked={archived} onCheckedChange={setArchived} />
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
    </>
  );
}

export function ClientDetailPage() {
  const { clientId } = useParams({ strict: false }) as { readonly clientId: string };
  const navigate = useNavigate();
  const { toast } = useToast();
  const client = useClient(clientId);
  const archive = useArchiveClient(clientId);
  const restore = useUpdateClient(clientId);
  const pluginTabs = usePluginSlot('clientTabs');
  const actions = useJobActions();
  const [tab, setTab] = useState(JOBS_TAB);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly job: JobOut | null }>({ open: false, job: null });
  const [exporting, setExporting] = useState(false);

  const crumbs = (
    <Link to="/clients" className="co-pagehead__crumb">
      <ArrowLeft size={14} aria-hidden="true" />
      {strings.clients.detail.back}
    </Link>
  );

  if (client.isPending) {
    return (
      <div className="co-page">
        <SkeletonGroup className="co-page">
          <Skeleton height={40} width="40%" radius="md" />
          <Skeleton height={140} radius="md" />
          <Skeleton height={320} radius="md" />
        </SkeletonGroup>
      </div>
    );
  }
  if (client.isError) {
    const notFound = client.error instanceof ApiError && client.error.status === 404;
    return (
      <div className="co-page">
        <PageHeader icon={Users} title={notFound ? strings.clients.detail.notFoundTitle : strings.clients.title} crumbs={crumbs} />
        <ErrorState
          error={client.error}
          title={notFound ? strings.clients.detail.notFoundTitle : undefined}
          description={notFound ? strings.clients.detail.notFoundLead : undefined}
          onRetry={notFound ? undefined : () => void client.refetch()}
        />
      </div>
    );
  }
  const data = client.data;

  const onArchive = async () => {
    setArchiveError(null);
    try {
      await archive.mutateAsync();
      toast({ tone: 'success', title: strings.clients.detail.archived, description: data.name });
      setArchiveOpen(false);
    } catch (caught) {
      setArchiveError(errorSentence(caught));
    }
  };
  const onRestore = () => {
    restore.mutate(
      { archived: false },
      {
        onSuccess: () => toast({ tone: 'success', title: strings.clients.detail.restored, description: data.name }),
        onError: (error) => toast({ tone: 'danger', title: strings.clients.detail.restore, description: errorSentence(error) }),
      },
    );
  };
  const onExport = async () => {
    setExporting(true);
    try {
      await exportJobs(data.id);
      toast({ tone: 'success', title: strings.jobs.exported });
    } catch (caught) {
      toast({ tone: 'danger', title: strings.jobs.exportFailed, description: errorSentence(caught) });
    } finally {
      setExporting(false);
    }
  };

  const tabs: TabItem[] = [
    {
      id: JOBS_TAB,
      label: strings.clients.detail.jobsTab,
      badge: data.job_count,
      content: <ClientJobs client={data} actions={actions} onNew={() => setDrawer({ open: true, job: null })} onEdit={(job) => setDrawer({ open: true, job })} />,
    },
    ...pluginTabs.map((item) => {
      const Component = item.component;
      return { id: item.id, label: item.label, content: <Component clientId={data.id} /> };
    }),
  ];

  return (
    <div className="co-page">
      <PageHeader
        icon={Users}
        title={data.name}
        crumbs={crumbs}
        badges={
          <>
            {data.worst_state && <SeverityBadge severity={STATE_SEVERITY[data.worst_state]} />}
            {data.archived && <span className="co-chip">{strings.clients.archived}</span>}
          </>
        }
        actions={
          <>
            <Button variant="secondary" iconStart={<Pencil size={16} />} onClick={() => setEditOpen(true)}>
              {strings.common.edit}
            </Button>
            <Button variant="secondary" iconStart={<Download size={16} />} onClick={() => void onExport()} loading={exporting} loadingLabel={strings.jobs.exporting}>
              {strings.clients.detail.exportCsv}
            </Button>
            {data.archived ? (
              <Button variant="secondary" iconStart={<ArchiveRestore size={16} />} onClick={onRestore} loading={restore.isPending}>
                {strings.clients.detail.restore}
              </Button>
            ) : (
              <Button variant="secondary" iconStart={<Archive size={16} />} onClick={() => setArchiveOpen(true)}>
                {strings.clients.detail.archive}
              </Button>
            )}
            <Button variant="danger" iconStart={<Trash2 size={16} />} onClick={() => setDeleteOpen(true)}>
              {strings.clients.detail.delete}
            </Button>
            {!data.archived && (
              <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, job: null })}>
                {strings.clients.detail.newJob}
              </Button>
            )}
          </>
        }
      />
      {data.archived && (
        <div className="co-banner" role="status">
          <span className="co-banner__icon">
            <Archive size={18} aria-hidden="true" />
          </span>
          {strings.clients.detail.archivedBanner}
        </div>
      )}
      <Summary client={data} />
      <Tabs label={strings.clients.detail.pluginTabs} items={tabs} value={tab} onValueChange={setTab} />

      <ClientDialog open={editOpen} onOpenChange={setEditOpen} client={data} />
      <DeleteClientDialog open={deleteOpen} onOpenChange={setDeleteOpen} client={data} onDeleted={() => void navigate({ to: '/clients' })} />
      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title={fill(strings.clients.detail.archiveTitle, { name: data.name })}
        description={strings.clients.detail.archiveLead}
        confirmLabel={strings.clients.detail.archive}
        busy={archive.isPending}
        error={archiveError}
        onConfirm={() => void onArchive()}
      />
      <JobDrawer open={drawer.open} job={drawer.job} presetClientId={data.id} onOpenChange={(open) => setDrawer((current) => ({ ...current, open }))} />
      {actions.dialogs}
    </div>
  );
}
