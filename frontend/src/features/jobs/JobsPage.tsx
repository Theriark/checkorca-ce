/**
 * /jobs: every job with filters by client, kind and state, search, the
 * archived toggle, the editor drawer, pause, resume and archive, and the CSV
 * import and export.
 */
import { Briefcase, Download, Plus, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';

import { JOB_KINDS, JOB_STATES, type JobKind, type JobOut, type JobState } from '../../api/jobs';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Switch } from '../../components/ui/Switch';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { ImportDialog } from './ImportDialog';
import { JobDrawer } from './JobDrawer';
import { JobsTable } from './JobsTable';
import { exportJobs } from './exportJobs';
import { kindLabel, stateLabel } from './jobState';
import { useJobList } from './queries';
import { useJobActions } from './useJobActions';
import '../features.css';

const ALL = 'all';

export function JobsPage() {
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [clientId, setClientId] = useState<string>(ALL);
  const [kind, setKind] = useState<string>(ALL);
  const [state, setState] = useState<string>(ALL);
  const [archived, setArchived] = useState(false);
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly job: JobOut | null }>({ open: false, job: null });
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const q = useDebouncedValue(search.trim(), 300);
  const clients = useClientOptions();
  const actions = useJobActions();

  const filters = useMemo(
    () => ({
      q,
      client_id: clientId === ALL ? null : clientId,
      kind: kind === ALL ? null : (kind as JobKind),
      state: state === ALL ? null : (state as JobState),
      archived,
    }),
    [q, clientId, kind, state, archived],
  );
  const list = useJobList(filters);
  const jobs = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const filtered = q || clientId !== ALL || kind !== ALL || state !== ALL;

  const onExport = async () => {
    setExporting(true);
    try {
      await exportJobs(filters.client_id);
      toast({ tone: 'success', title: strings.jobs.exported });
    } catch (caught) {
      toast({ tone: 'danger', title: strings.jobs.exportFailed, description: errorSentence(caught) });
    } finally {
      setExporting(false);
    }
  };

  const count = jobs.length;
  const lead = list.isSuccess ? (count === 1 ? strings.jobs.countOne : fill(strings.jobs.count, { count })) : strings.jobs.lead;

  return (
    <div className="co-page">
      <PageHeader
        icon={Briefcase}
        title={strings.jobs.title}
        lead={lead}
        actions={
          <>
            <Button variant="secondary" iconStart={<Upload size={16} />} onClick={() => setImportOpen(true)}>
              {strings.jobs.importCsv}
            </Button>
            <Button variant="secondary" iconStart={<Download size={16} />} onClick={() => void onExport()} loading={exporting} loadingLabel={strings.jobs.exporting}>
              {strings.jobs.exportCsv}
            </Button>
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, job: null })}>
              {strings.jobs.new}
            </Button>
          </>
        }
      />

      <JobsTable
        tableId="jobs"
        jobs={jobs}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        showClient
        onEdit={(job) => setDrawer({ open: true, job })}
        actions={actions}
        emptyTitle={archived ? strings.jobs.emptyArchived : filtered ? strings.jobs.noMatch : strings.jobs.emptyTitle}
        emptyDescription={filtered ? strings.jobs.noMatchLead : archived ? undefined : strings.jobs.emptyLead}
        emptyAction={
          !filtered && !archived ? (
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, job: null })}>
              {strings.jobs.new}
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
              label={strings.jobs.client}
              hideLabel
              size="sm"
              value={clientId}
              onValueChange={setClientId}
              options={[{ value: ALL, label: strings.jobs.anyClient }, ...(clients.data ?? []).map((client) => ({ value: client.id, label: client.name }))]}
            />
            <Select
              className="co-filters__select"
              label={strings.jobs.kind}
              hideLabel
              size="sm"
              value={kind}
              onValueChange={setKind}
              options={[{ value: ALL, label: strings.jobs.anyKind }, ...JOB_KINDS.map((item) => ({ value: item, label: kindLabel(item) }))]}
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

      <JobDrawer open={drawer.open} job={drawer.job} onOpenChange={(open) => setDrawer((current) => ({ ...current, open }))} />
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} />
      {actions.dialogs}
    </div>
  );
}
