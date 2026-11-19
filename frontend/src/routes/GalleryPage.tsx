/**
 * The component gallery: every component of components/ui in every state,
 * for the Playwright axe and screenshot run. Built only with VITE_GALLERY=1
 * (npm run build:e2e); the product image never contains it.
 */
import { Bell, Plus, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { ApiError } from '../api/client';
import { Sparkline } from '../charts/Sparkline';
import {
  Button,
  CommandSearch,
  CoverageRing,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  SEVERITIES,
  Select,
  SeverityBadge,
  Skeleton,
  SkeletonGroup,
  SkeletonText,
  StatCard,
  useToast,
  type CommandItem,
  type DataTableColumn,
} from '../components/ui';
import { NightRibbonMark } from '../ribbon/NightRibbonMark';
import { Logo } from '../shell/Logo';
import { ThemeToggle } from '../shell/ThemeToggle';
import { strings } from '../strings';
import './routes.css';

interface JobRow {
  readonly id: string;
  readonly client: string;
  readonly job: string;
  readonly state: (typeof SEVERITIES)[number];
  readonly lastSuccess: string;
  readonly runs: number;
}

const ROWS: readonly JobRow[] = [
  { id: 'j1', client: 'Harbourside Dental (fictional)', job: 'Veeam nightly', state: 'verified', lastSuccess: '02:14', runs: 14 },
  { id: 'j2', client: 'Northwind Legal (fictional)', job: 'Synology ABB', state: 'silent', lastSuccess: 'Yesterday 01:50', runs: 13 },
  { id: 'j3', client: 'Blue Fern Studio (fictional)', job: 'Acronis cloud', state: 'failed', lastSuccess: '3 days ago', runs: 11 },
  { id: 'j4', client: 'Harbourside Dental (fictional)', job: 'SQL dump script', state: 'warning', lastSuccess: '23:05', runs: 14 },
  { id: 'j5', client: 'Orchard Clinic (fictional)', job: 'MSP360 files', state: 'paused', lastSuccess: '12 days ago', runs: 2 },
  { id: 'j6', client: 'Northwind Legal (fictional)', job: 'Cove server', state: 'overdue', lastSuccess: '00:40', runs: 14 },
];

const COLUMNS: readonly DataTableColumn<JobRow>[] = [
  { id: 'client', header: 'Client', cell: (row) => row.client, sortValue: (row) => row.client },
  { id: 'job', header: 'Job', cell: (row) => row.job, sortValue: (row) => row.job },
  { id: 'state', header: 'State', cell: (row) => <SeverityBadge severity={row.state} />, sortValue: (row) => row.state },
  { id: 'last', header: 'Last success', cell: (row) => row.lastSuccess, numeric: true },
  { id: 'runs', header: 'Runs (14 d)', cell: (row) => row.runs, sortValue: (row) => row.runs, align: 'end', numeric: true },
];

const SPARK_MANY = [12, 13, 13, 14, 11, 12, 15, 14, 14, 16, 15, 13, 14, 17];
const PROBLEM = new ApiError(
  { type: 'about:blank', title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-3f9c2a' },
);
const OFFLINE = new ApiError({ type: 'about:blank', title: 'No answer from the server', status: 0 });

function Case({ title, children, className }: { readonly title: string; readonly children: ReactNode; readonly className?: string }) {
  return (
    <div className={className ? `co-gallery__case ${className}` : 'co-gallery__case'}>
      <span className="co-gallery__case-title">{title}</span>
      {children}
    </div>
  );
}

function Section({ id, title, children, wide = false }: { readonly id: string; readonly title: string; readonly children: ReactNode; readonly wide?: boolean }) {
  return (
    <section id={id} className="co-gallery__section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="co-gallery__section-title">
        {title}
      </h2>
      <div className={wide ? 'co-gallery__grid co-gallery__grid--wide' : 'co-gallery__grid'}>{children}</div>
    </section>
  );
}

function ToastCases() {
  const { toast } = useToast();
  return (
    <div className="co-gallery__row">
      <Button onClick={() => toast({ tone: 'success', title: 'Client saved' })}>Success toast</Button>
      <Button onClick={() => toast({ tone: 'danger', title: 'Export failed', description: 'Request id req-77a1' })}>Error toast</Button>
      <Button onClick={() => toast({ tone: 'info', title: 'Worker heartbeat is 90 seconds old' })}>Info toast</Button>
    </div>
  );
}

export function GalleryPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dangerOpen, setDangerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectValue, setSelectValue] = useState<string | undefined>('cron');
  const commands: readonly CommandItem[] = [
    { id: 'clients', label: 'Clients', group: 'sections', run: () => undefined },
    { id: 'jobs', label: 'Jobs', group: 'sections', run: () => undefined },
    { id: 'theme', label: 'Switch theme', group: 'actions', run: () => undefined },
  ];

  return (
    <div className="co-gallery">
      <header className="co-gallery__header">
        <Logo variant="horizontal" width={168} />
        <ThemeToggle />
      </header>
      <main className="co-gallery__main">
        <div>
          <h1>{strings.gallery.title}</h1>
          <p className="text-secondary">{strings.gallery.lead}</p>
        </div>

        <Section id="buttons" title="Button">
          <Case title="Variants">
            <div className="co-gallery__row">
              <Button variant="primary">Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger" iconStart={<Trash2 size={16} />}>
                Delete client
              </Button>
            </div>
          </Case>
          <Case title="States">
            <div className="co-gallery__row">
              <Button variant="primary" loading loadingLabel="Saving">
                Save
              </Button>
              <Button variant="primary" disabled>
                Disabled
              </Button>
              <Button size="sm" iconStart={<Plus size={14} />}>
                Small
              </Button>
              <Button iconOnly iconStart={<Bell size={18} />}>
                Notifications
              </Button>
            </div>
          </Case>
        </Section>

        <Section id="fields" title="Input and Select">
          <Case title="Default and hint">
            <Input label="Client name" placeholder="Harbourside Dental" hint="Shown on the morning check and in the digest." />
          </Case>
          <Case title="Error">
            <Input label="E-mail address" type="email" defaultValue="not-an-address" error="Enter a valid e-mail address." />
          </Case>
          <Case title="Mono and disabled">
            <Input label="Cron expression" mono defaultValue="0 23 * * 1-5" />
            <Input label="Ping token" mono defaultValue="chk_rY8w…" disabled optionalLabel={strings.common.optional} />
          </Case>
          <Case title="Select">
            <Select
              label="Schedule kind"
              value={selectValue}
              onValueChange={setSelectValue}
              options={[
                { value: 'cron', label: 'Cron' },
                { value: 'interval', label: 'Interval' },
                { value: 'daily', label: 'Daily list' },
              ]}
              hint="How the expected times are computed."
            />
            <Select label="Time zone" value={undefined} onValueChange={() => undefined} placeholder="Pick a zone" options={[{ value: 'lisbon', label: 'Europe/Lisbon' }]} error="Pick a time zone." />
          </Case>
        </Section>

        <Section id="badges" title="SeverityBadge">
          <Case title="Every state (icon, word, colour)" className="co-gallery__case--wide">
            <div className="co-gallery__row">
              {SEVERITIES.map((severity) => (
                <SeverityBadge key={severity} severity={severity} />
              ))}
            </div>
          </Case>
          <Case title="Small, with detail">
            <div className="co-gallery__row">
              <SeverityBadge severity="failed" size="sm" detail="3" />
              <SeverityBadge severity="silent" size="sm" detail="2" />
              <SeverityBadge severity="verified" size="sm" detail="41" />
            </div>
          </Case>
        </Section>

        <Section id="stats" title="StatCard and charts">
          <Case title="Ready, good rise">
            <StatCard label="Verified" value={41} delta={3} spark={SPARK_MANY} goodWhen="up" />
          </Case>
          <Case title="Ready, bad rise">
            <StatCard label="Failed" value={3} delta={2} spark={[0, 1, 0, 0, 2, 1, 0, 1, 1, 0, 0, 1, 2, 3]} goodWhen="down" />
          </Case>
          <Case title="One point">
            <StatCard label="Silent" value={2} delta={0} spark={[2]} goodWhen="down" />
          </Case>
          <Case title="No history">
            <StatCard label="Unmatched" value={0} spark={[]} />
          </Case>
          <Case title="Loading">
            <StatCard label="Paused" value={null} loading />
          </Case>
          <Case title="Sparkline alone: many, one, none">
            <div className="co-gallery__row">
              <Sparkline values={SPARK_MANY} label="Many points" tone="success" />
              <Sparkline values={[5]} label="One point" tone="warning" />
              <Sparkline values={[]} label="No points" />
            </div>
          </Case>
        </Section>

        <Section id="coverage" title="CoverageRing">
          <Case title="Good">
            <CoverageRing verified={46} expected={48} />
          </Case>
          <Case title="Warning">
            <CoverageRing verified={40} expected={48} />
          </Case>
          <Case title="Danger, standalone">
            <CoverageRing verified={20} expected={48} standalone size={112} />
          </Case>
          <Case title="Empty">
            <CoverageRing verified={0} expected={0} />
          </Case>
          <Case title="Loading">
            <CoverageRing verified={0} expected={0} loading />
          </Case>
        </Section>

        <Section id="skeleton" title="Skeleton">
          <Case title="Blocks and text">
            <SkeletonGroup>
              <Skeleton height={24} width="40%" />
              <SkeletonText lines={3} />
              <Skeleton height={40} radius="pill" width={120} />
            </SkeletonGroup>
          </Case>
        </Section>

        <Section id="states" title="EmptyState and ErrorState" wide>
          <Case title="Empty, first-run checklist">
            <EmptyState
              title="No clients yet"
              description="Three steps and the first ring appears on the ribbon."
              steps={['Add a client', 'Create an inbox', 'Send a test mail']}
              action={<Button variant="primary">Add a client</Button>}
            />
          </Case>
          <Case title="Empty, compact with the mark">
            <EmptyState compact visual="mark" title="No unmatched mail" description="Every result of the night found its job." />
          </Case>
          <Case title="Error with request id and retry">
            <ErrorState error={PROBLEM} onRetry={() => undefined} />
          </Case>
          <Case title="Offline, compact">
            <ErrorState error={OFFLINE} onRetry={() => undefined} compact />
          </Case>
        </Section>

        <Section id="table" title="DataTable" wide>
          <Case title="Ready: sticky header, sort, density, saved views" className="co-gallery__case--full">
            <DataTable
              tableId="gallery-jobs"
              caption="Jobs of the fictional demo clients"
              columns={COLUMNS}
              rows={ROWS}
              getRowId={(row) => row.id}
              defaultSort={{ column: 'client', direction: 'asc' }}
              toolbar={<Input label="Search jobs" placeholder="Search" />}
            />
          </Case>
          <Case title="Loading">
            <DataTable tableId="gallery-loading" caption="Loading jobs" columns={COLUMNS} rows={[]} getRowId={(row) => row.id} loading skeletonRows={3} />
          </Case>
          <Case title="Empty">
            <DataTable
              tableId="gallery-empty"
              caption="No jobs"
              columns={COLUMNS}
              rows={[]}
              getRowId={(row) => row.id}
              emptyTitle="No jobs yet"
              emptyDescription="Create one from a client or import a CSV."
              emptyAction={<Button variant="primary">Create job</Button>}
            />
          </Case>
          <Case title="Error">
            <DataTable tableId="gallery-error" caption="Jobs failed to load" columns={COLUMNS} rows={[]} getRowId={(row) => row.id} error={PROBLEM} onRetry={() => undefined} />
          </Case>
        </Section>

        <Section id="overlays" title="Dialog, Toast, CommandSearch">
          <Case title="Dialog">
            <div className="co-gallery__row">
              <Button onClick={() => setDialogOpen(true)}>Open dialog</Button>
              <Button variant="danger" onClick={() => setDangerOpen(true)}>
                Destructive confirm
              </Button>
            </div>
            <Dialog
              open={dialogOpen}
              onOpenChange={setDialogOpen}
              title="Pause job"
              description="The job stops expecting results until you resume it."
              footer={
                <>
                  <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                    {strings.common.cancel}
                  </Button>
                  <Button variant="primary" onClick={() => setDialogOpen(false)}>
                    Pause
                  </Button>
                </>
              }
            >
              <Input label="Until" type="date" optionalLabel={strings.common.optional} />
            </Dialog>
            <Dialog
              open={dangerOpen}
              onOpenChange={setDangerOpen}
              tone="danger"
              title="Delete Harbourside Dental"
              description="Removes the client, its jobs and all history. Type the client name to confirm."
              footer={
                <>
                  <Button variant="ghost" onClick={() => setDangerOpen(false)}>
                    {strings.common.cancel}
                  </Button>
                  <Button variant="danger" onClick={() => setDangerOpen(false)}>
                    {strings.common.delete}
                  </Button>
                </>
              }
            >
              <Input label="Client name" placeholder="Harbourside Dental" />
            </Dialog>
          </Case>
          <Case title="Toast">
            <ToastCases />
          </Case>
          <Case title="CommandSearch">
            <Button onClick={() => setSearchOpen(true)}>Open command search</Button>
            <CommandSearch items={commands} open={searchOpen} onOpenChange={setSearchOpen} />
          </Case>
        </Section>

        <Section id="ribbon" title="Night Ribbon mark">
          <Case title="Empty-state variant">
            <NightRibbonMark variant="empty" width={300} />
          </Case>
        </Section>
      </main>
    </div>
  );
}
