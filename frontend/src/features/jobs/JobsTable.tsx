/**
 * The jobs list used on /jobs and on the client page: name and client,
 * kind, schedule in mono with its zone, the state badge (with the pause end
 * when there is one) and a row action menu. A click or Enter on a row opens
 * the editor.
 */
import { Link, useNavigate } from '@tanstack/react-router';
import { Archive, ArchiveRestore, Copy, ExternalLink, Pause, Pencil, Play } from 'lucide-react';
import type { ReactNode } from 'react';

import type { JobOut } from '../../api/jobs';
import { ActionMenu, type ActionItem } from '../../components/ui/ActionMenu';
import { DataTable } from '../../components/ui/DataTable';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { fill, formatAgo, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { STATE_SEVERITY, kindLabel, scheduleKindLabel } from './jobState';
import { isPaused } from './queries';
import type { JobActions } from './useJobActions';
import '../features.css';

export interface JobsTableProps {
  readonly tableId: string;
  readonly jobs: readonly JobOut[];
  readonly loading: boolean;
  readonly error?: unknown;
  readonly onRetry?: () => void;
  readonly toolbar?: ReactNode;
  readonly emptyTitle: ReactNode;
  readonly emptyDescription?: ReactNode;
  readonly emptyAction?: ReactNode;
  /** Hide the client column on the client's own page. */
  readonly showClient?: boolean;
  readonly onEdit: (job: JobOut) => void;
  readonly actions: JobActions;
}

function StateCell({ job }: { readonly job: JobOut }) {
  const paused = isPaused(job);
  return (
    <span className="co-cell-state">
      <SeverityBadge severity={STATE_SEVERITY[job.state]} size="sm" />
      {paused && (
        <span className="co-cell-state__note">
          {job.paused_until ? fill(strings.jobs.pausedUntil, { time: formatDateTime(job.paused_until) }) : strings.jobs.pausedUntilResumed}
        </span>
      )}
      {job.archived && <span className="co-chip">{strings.jobs.archived}</span>}
    </span>
  );
}

export function JobsTable({
  tableId,
  jobs,
  loading,
  error,
  onRetry,
  toolbar,
  emptyTitle,
  emptyDescription,
  emptyAction,
  showClient = true,
  onEdit,
  actions,
}: JobsTableProps) {
  const navigate = useNavigate();
  const onOpen = (job: JobOut) => void navigate({ to: '/jobs/$jobId', params: { jobId: job.id } });
  const menuFor = (job: JobOut): readonly ActionItem[] => {
    const paused = isPaused(job);
    return [
      { id: 'open', label: strings.jobs.open, icon: <ExternalLink size={16} />, onSelect: () => onOpen(job) },
      { id: 'edit', label: strings.jobs.edit, icon: <Pencil size={16} />, onSelect: () => onEdit(job) },
      paused
        ? { id: 'resume', label: strings.jobs.resume, icon: <Play size={16} />, onSelect: () => actions.resume(job) }
        : { id: 'pause', label: strings.jobs.pause, icon: <Pause size={16} />, onSelect: () => actions.pause(job) },
      { id: 'copy', label: strings.jobs.copyPing, icon: <Copy size={16} />, onSelect: () => actions.copyPing(job), disabled: !job.ping_url },
      job.archived
        ? { id: 'restore', label: strings.jobs.restore, icon: <ArchiveRestore size={16} />, onSelect: () => actions.restore(job), separatorBefore: true }
        : { id: 'archive', label: strings.jobs.archive, icon: <Archive size={16} />, onSelect: () => actions.archive(job), separatorBefore: true },
    ];
  };

  const columns: DataTableColumn<JobOut>[] = [
    {
      id: 'name',
      header: strings.jobs.columns.job,
      sortValue: (job) => job.name,
      cell: (job) => (
        <span className="co-cell-title">
          <Link to="/jobs/$jobId" params={{ jobId: job.id }} className="co-cell-title__name" onClick={(event) => event.stopPropagation()}>
            {job.name}
          </Link>
          {showClient && <span className="co-cell-title__sub">{job.client_name}</span>}
        </span>
      ),
    },
    { id: 'kind', header: strings.jobs.columns.kind, sortValue: (job) => job.kind, cell: (job) => kindLabel(job.kind) },
    {
      id: 'schedule',
      header: strings.jobs.columns.schedule,
      sortValue: (job) => `${job.schedule_kind} ${job.schedule_expr}`,
      cell: (job) => (
        <span className="co-cell-schedule">
          <span className="co-cell-schedule__expr">
            <span className="co-cell-muted">{scheduleKindLabel(job.schedule_kind)}</span> <code>{job.schedule_expr}</code>
          </span>
          <span className="co-cell-schedule__zone">{job.timezone}</span>
        </span>
      ),
    },
    { id: 'state', header: strings.jobs.columns.state, sortValue: (job) => job.state, cell: (job) => <StateCell job={job} /> },
    {
      id: 'last',
      header: strings.jobs.columns.lastSuccess,
      numeric: true,
      // Sortable since the evaluator (C7) fills it; the exact time with how
      // long ago under it, so "3 days ago" reads at a glance.
      sortValue: (job) => job.last_success_at ?? null,
      cell: (job) =>
        job.last_success_at ? (
          <span className="co-cell-schedule">
            <span className="co-cell-schedule__expr">{formatDateTime(job.last_success_at)}</span>
            <span className="co-cell-schedule__zone">{formatAgo(job.last_success_at)}</span>
          </span>
        ) : (
          <span className="co-cell-muted">{strings.jobs.notYet}</span>
        ),
    },
    {
      id: 'actions',
      header: <span className="sr-only">{strings.jobs.columns.actions}</span>,
      align: 'end',
      width: '56px',
      cell: (job) => (
        <span className="co-cell-actions">
          <ActionMenu label={fill(strings.jobs.actionsFor, { name: job.name })} items={menuFor(job)} />
        </span>
      ),
    },
  ];

  return (
    <DataTable
      tableId={tableId}
      caption={strings.jobs.tableCaption}
      columns={columns}
      rows={jobs}
      getRowId={(job) => job.id}
      loading={loading}
      error={error}
      onRetry={onRetry}
      toolbar={toolbar}
      emptyTitle={emptyTitle}
      emptyDescription={emptyDescription}
      emptyAction={emptyAction}
      onRowClick={onEdit}
      minWidth={showClient ? 760 : 680}
    />
  );
}
