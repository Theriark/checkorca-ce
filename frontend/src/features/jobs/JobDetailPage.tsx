/**
 * /jobs/:id: the job's state (badge, since, last success, acknowledged
 * time: the API answers no name), the 30-day strip, the schedule, the
 * history (runs of the last 30 days and every state change) and the newest
 * message as escaped text. Acknowledge, pause or resume, edit, archive or
 * restore from the header.
 */
import { Link, useParams } from '@tanstack/react-router';
import { Archive, ArchiveRestore, ArrowLeft, Briefcase, Check, Pause, Pencil, Play } from 'lucide-react';
import { useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import type { FlipOut, JobOut, OccurrenceOut } from '../../api/jobs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { CopyField } from '../../components/ui/CopyField';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { Tabs } from '../../components/ui/Tabs';
import { useToast } from '../../components/ui/useToast';
import { fill, formatAgo, formatDateTime, formatShortDateTime } from '../../lib/format';
import { OccurrenceBadge } from '../../ribbon/OccurrenceBadge';
import { strings } from '../../strings';
import { useAcknowledgeJob } from '../dashboard/queries';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { useRawMessage } from '../unmatched/queries';
import { DayStrip } from './DayStrip';
import { JobDrawer } from './JobDrawer';
import { startOfDayAgo } from './dayStrip';
import { STATE_SEVERITY, kindLabel, scheduleKindLabel, warningPolicyLabel } from './jobState';
import { isPaused, useFlips, useJob, useJobResults, useOccurrences } from './queries';
import { useJobActions } from './useJobActions';
import '../features.css';
import '../dashboard/dashboard.css';

const STRIP_DAYS = 30;
const RUNS_TAB = 'runs';
const FLIPS_TAB = 'flips';

function Crumbs({ job }: { readonly job?: JobOut }) {
  return (
    <>
      <Link to="/jobs" className="co-pagehead__crumb">
        <ArrowLeft size={14} aria-hidden="true" />
        {strings.jobDetail.back}
      </Link>
      {job && (
        <Link to="/clients/$clientId" params={{ clientId: job.client_id }} className="co-pagehead__crumb">
          {job.client_name}
        </Link>
      )}
    </>
  );
}

function StateCard({ job }: { readonly job: JobOut }) {
  const copy = strings.jobDetail;
  return (
    <section className="co-card" aria-labelledby="job-state-title">
      <h2 id="job-state-title" className="co-card__title">
        {copy.stateTitle}
      </h2>
      <dl className="co-kv">
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.jobs.state}</dt>
          <dd className="co-kv__value">
            <span className="co-job__state">
              <SeverityBadge severity={STATE_SEVERITY[job.state]} />
              {job.state_since && <span className="co-summary__muted tabular">{fill(copy.stateSince, { time: formatShortDateTime(job.state_since) })}</span>}
            </span>
          </dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.lastSuccess}</dt>
          <dd className="co-kv__value tabular">{job.last_success_at ? `${formatDateTime(job.last_success_at)} (${formatAgo(job.last_success_at)})` : <span className="co-summary__muted">{strings.jobs.notYet}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.acknowledgedAt}</dt>
          <dd className="co-kv__value">
            {job.acknowledged_at ? (
              <span className="co-job__state">
                <span className="co-job__ack tabular" data-testid="acknowledged-at">
                  <Check size={14} aria-hidden="true" />
                  {formatDateTime(job.acknowledged_at)}
                </span>
                <span className="co-job__ack-note">{copy.acknowledgedBy}</span>
              </span>
            ) : (
              <span className="co-summary__muted">{copy.notAcknowledged}</span>
            )}
          </dd>
        </div>
        {isPaused(job) && (
          <div className="co-kv__item">
            <dt className="co-kv__label">{strings.badge.paused}</dt>
            <dd className="co-kv__value">{job.paused_until ? fill(strings.jobs.pausedUntil, { time: formatDateTime(job.paused_until) }) : strings.jobs.pausedUntilResumed}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}

function ScheduleCard({ job }: { readonly job: JobOut }) {
  const copy = strings.jobDetail;
  return (
    <section className="co-card" aria-labelledby="job-schedule-title">
      <h2 id="job-schedule-title" className="co-card__title">
        {copy.scheduleTitle}
      </h2>
      <dl className="co-kv">
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.kind}</dt>
          <dd className="co-kv__value">{scheduleKindLabel(job.schedule_kind)}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.expression}</dt>
          <dd className="co-kv__value mono co-kv__value--mono">{job.schedule_expr}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.zone}</dt>
          <dd className="co-kv__value">{job.timezone}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.maxRuntime}</dt>
          <dd className="co-kv__value tabular">{fill(copy.minutes, { count: job.max_runtime_minutes })}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.grace}</dt>
          <dd className="co-kv__value tabular">{fill(copy.minutes, { count: job.grace_minutes })}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.escalate}</dt>
          <dd className="co-kv__value tabular">{fill(copy.minutes, { count: job.escalate_minutes })}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.basis}</dt>
          <dd className="co-kv__value">{copy.basisWords[job.attribution_basis]}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.warnings}</dt>
          <dd className="co-kv__value">{warningPolicyLabel(job.warning_policy)}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.threshold}</dt>
          <dd className="co-kv__value tabular">{job.consecutive_failures_to_alert}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.pack}</dt>
          <dd className="co-kv__value">{job.parser_pack_id ? <span className="mono">{job.parser_pack_id}</span> : <span className="co-summary__muted">{copy.noPack}</span>}</dd>
        </div>
        <div className="co-kv__item co-kv__item--wide">
          <dt className="co-kv__label">{copy.matchKey}</dt>
          <dd className="co-kv__value">{job.match_key ? <span className="mono">{job.match_key}</span> : <span className="co-summary__muted">{copy.noMatchKey}</span>}</dd>
        </div>
      </dl>
      <CopyField label={copy.pingTitle} value={job.ping_url} unavailable={strings.jobForm.pingUnavailable} hint={strings.jobForm.pingLead} />

    </section>
  );
}

function RunsTable({ runs }: { readonly runs: readonly OccurrenceOut[] }) {
  const copy = strings.jobDetail;
  if (runs.length === 0) {
    return <p className="co-summary__muted">{copy.runsEmpty}</p>;
  }
  return (
    <div className="co-table__scroll" tabIndex={0}>
      <table className="co-import__table">
        <caption className="sr-only">{copy.runsTab}</caption>
        <thead>
          <tr>
            <th scope="col">{copy.runColumns.scheduled}</th>
            <th scope="col">{copy.runColumns.deadline}</th>
            <th scope="col">{copy.runColumns.state}</th>
            <th scope="col">{copy.runColumns.note}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.scheduled_for} data-state={run.state}>
              <td className="tabular">{formatShortDateTime(run.scheduled_for)}</td>
              <td className="tabular">{formatShortDateTime(run.deadline)}</td>
              <td>
                <OccurrenceBadge state={run.state} size="sm" />
              </td>
              <td>{run.note ?? <span className="co-cell-muted">{strings.common.none}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FlipsTable({ flips }: { readonly flips: readonly FlipOut[] }) {
  const copy = strings.jobDetail;
  if (flips.length === 0) {
    return <p className="co-summary__muted">{copy.flipsEmpty}</p>;
  }
  return (
    <div className="co-table__scroll" tabIndex={0}>
      <table className="co-import__table">
        <caption className="sr-only">{copy.flipsTab}</caption>
        <thead>
          <tr>
            <th scope="col">{copy.flipColumns.at}</th>
            <th scope="col">{copy.flipColumns.from}</th>
            <th scope="col">{copy.flipColumns.to}</th>
            <th scope="col">{copy.flipColumns.reason}</th>
          </tr>
        </thead>
        <tbody>
          {flips.map((flip) => (
            <tr key={flip.id}>
              <td className="tabular">{formatShortDateTime(flip.at)}</td>
              <td>
                <SeverityBadge severity={STATE_SEVERITY[flip.from_state]} size="sm" />
              </td>
              <td>
                <SeverityBadge severity={STATE_SEVERITY[flip.to_state]} size="sm" />
              </td>
              <td>{flip.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LatestMessage({ jobId, enabled }: { readonly jobId: string; readonly enabled: boolean }) {
  const copy = strings.jobDetail;
  const results = useJobResults(jobId, enabled);
  const messageId = useMemo(() => results.data?.items.find((item) => item.raw_message_id)?.raw_message_id ?? null, [results.data]);
  const message = useRawMessage(messageId);
  let body: React.ReactNode;
  if (results.isPending || (messageId && message.isPending)) {
    body = (
      <SkeletonGroup className="co-dash__list-skeleton">
        <Skeleton height={16} width="50%" />
        <Skeleton height={120} radius="md" />
      </SkeletonGroup>
    );
  } else if (results.isLoadingError) {
    body = <ErrorState error={results.error} onRetry={() => void results.refetch()} compact />;
  } else if (!messageId) {
    body = <p className="co-summary__muted">{copy.rawNone}</p>;
  } else if (message.isError) {
    body = message.error instanceof ApiError && message.error.status === 404 ? <p className="co-summary__muted">{copy.rawGone}</p> : <ErrorState error={message.error} onRetry={() => void message.refetch()} compact />;
  } else if (message.data) {
    body = (
      <>
        <p className="co-digest__subject">
          <span className="co-digest__subject-label">{strings.messages.columns.subject}</span> <span className="co-digest__subject-text">{message.data.subject || strings.messages.noSubject}</span>
        </p>
        {message.data.text_truncated && <Alert tone="info">{strings.messages.detail.truncated}</Alert>}
        {message.data.text.length === 0 ? (
          <p className="co-summary__muted">{strings.messages.detail.bodyEmpty}</p>
        ) : (
          <div className="co-raw" tabIndex={0}>
            <pre className="co-raw__pre" data-testid="job-raw-message">
              {message.data.text}
            </pre>
          </div>
        )}
        <p>
          <Link to="/messages/$messageId" params={{ messageId }}>
            {copy.rawOpen}
          </Link>
        </p>
      </>
    );
  }
  return (
    <section className="co-card" aria-labelledby="job-raw-title">
      <div className="co-card__head">
        <h2 id="job-raw-title" className="co-card__title">
          {copy.rawTitle}
        </h2>
        <p className="co-card__lead">{copy.rawLead}</p>
      </div>
      {body}
    </section>
  );
}

export function JobDetailPage() {
  const { jobId } = useParams({ strict: false }) as { readonly jobId: string };
  const copy = strings.jobDetail;
  const { toast } = useToast();
  const job = useJob(jobId);
  // Moves with every poll of the job, so the strip rolls over at midnight.
  const now = useMemo(() => (job.dataUpdatedAt ? new Date(job.dataUpdatedAt) : new Date()), [job.dataUpdatedAt]);
  const from = useMemo(() => startOfDayAgo(now, STRIP_DAYS - 1).toISOString(), [now]);
  const to = useMemo(() => startOfDayAgo(now, -1).toISOString(), [now]);
  // A failed poll keeps the job on screen; the dependent lists follow the
  // data, not the last fetch.
  const loaded = job.data !== undefined;
  const occurrences = useOccurrences(jobId, from, to, loaded);
  const flips = useFlips({ job_id: jobId }, loaded);
  const acknowledge = useAcknowledgeJob();
  const actions = useJobActions();
  const [editOpen, setEditOpen] = useState(false);
  const [tab, setTab] = useState(RUNS_TAB);
  const runs = useMemo(() => [...(occurrences.data ?? [])].sort((a, b) => b.scheduled_for.localeCompare(a.scheduled_for)), [occurrences.data]);
  const flipItems = useMemo(() => flips.data?.pages.flatMap((page) => page.items) ?? [], [flips.data]);

  if (job.isPending) {
    return (
      <div className="co-page">
        <PageHeader icon={Briefcase} title={<Skeleton width={280} height={28} />} crumbs={<Crumbs />} />
        <SkeletonGroup className="co-stack">
          <Skeleton height={140} radius="md" />
          <Skeleton height={120} radius="md" />
          <Skeleton height={320} radius="md" />
        </SkeletonGroup>
      </div>
    );
  }
  if (job.isLoadingError) {
    const notFound = job.error instanceof ApiError && job.error.status === 404;
    return (
      <div className="co-page">
        <PageHeader icon={Briefcase} title={notFound ? copy.notFoundTitle : strings.jobs.title} crumbs={<Crumbs />} />
        {notFound ? <ErrorState title={copy.notFoundTitle} description={copy.notFoundLead} /> : <ErrorState error={job.error} onRetry={() => void job.refetch()} retrying={job.isFetching} />}
      </div>
    );
  }
  const data = job.data;
  const paused = isPaused(data);
  const canAcknowledge = !data.acknowledged_at && (data.state === 'warning' || data.state === 'failing' || data.state === 'missed');

  const onAcknowledge = () => {
    void acknowledge
      .mutateAsync(data.id)
      .then(() => toast({ tone: 'success', title: strings.dashboard.acknowledgedToast, description: `${data.name}. ${strings.dashboard.acknowledgedLead}` }))
      .catch((error: unknown) => toast({ tone: 'danger', title: strings.dashboard.acknowledgeFailed, description: errorSentence(error) }));
  };

  return (
    <div className="co-page">
      <PageHeader
        icon={Briefcase}
        title={data.name}
        lead={`${data.client_name} · ${kindLabel(data.kind)}`}
        crumbs={<Crumbs job={data} />}
        badges={
          <>
            <SeverityBadge severity={STATE_SEVERITY[data.state]} />
            {paused && <span className="co-chip">{data.paused_until ? fill(strings.jobs.pausedUntil, { time: formatDateTime(data.paused_until) }) : strings.jobs.pausedUntilResumed}</span>}
            {data.archived && <span className="co-chip">{strings.jobs.archived}</span>}
          </>
        }
        actions={
          <>
            {canAcknowledge && (
              <Button variant="primary" iconStart={<Check size={16} />} onClick={onAcknowledge} loading={acknowledge.isPending} loadingLabel={strings.dashboard.acknowledging}>
                {strings.dashboard.acknowledge}
              </Button>
            )}
            {!data.archived &&
              (paused ? (
                <Button variant="secondary" iconStart={<Play size={16} />} onClick={() => actions.resume(data)}>
                  {strings.jobs.resume}
                </Button>
              ) : (
                <Button variant="secondary" iconStart={<Pause size={16} />} onClick={() => actions.pause(data)}>
                  {strings.jobs.pause}
                </Button>
              ))}
            <Button variant="secondary" iconStart={<Pencil size={16} />} onClick={() => setEditOpen(true)}>
              {copy.edit}
            </Button>
            {data.archived ? (
              <Button variant="secondary" iconStart={<ArchiveRestore size={16} />} onClick={() => actions.restore(data)}>
                {strings.jobs.restore}
              </Button>
            ) : (
              <Button variant="secondary" iconStart={<Archive size={16} />} onClick={() => actions.archive(data)}>
                {strings.jobs.archive}
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
          {copy.archivedBanner}
        </div>
      )}

      <StateCard job={data} />

      <section className="co-card" aria-labelledby="job-strip-title">
        <div className="co-card__head">
          <h2 id="job-strip-title" className="co-card__title">
            {copy.stripTitle}
          </h2>
          <p className="co-card__lead">{copy.stripLead}</p>
        </div>
        {occurrences.isPending ? (
          <SkeletonGroup>
            <Skeleton height={40} radius="md" />
          </SkeletonGroup>
        ) : occurrences.isLoadingError ? (
          <ErrorState error={occurrences.error} onRetry={() => void occurrences.refetch()} compact />
        ) : occurrences.data.length === 0 ? (
          <EmptyState compact visual="none" title={copy.stripEmptyTitle} description={copy.stripEmptyLead} />
        ) : (
          <DayStrip occurrences={occurrences.data} now={now} days={STRIP_DAYS} />
        )}
      </section>

      <div className="co-job__grid">
        <section className="co-card" aria-labelledby="job-history-title">
          <div className="co-card__head">
            <h2 id="job-history-title" className="co-card__title">
              {copy.historyTitle}
            </h2>
            <p className="co-card__lead">{copy.historyLead}</p>
          </div>
          <Tabs
            label={copy.historyTitle}
            value={tab}
            onValueChange={setTab}
            items={[
              {
                id: RUNS_TAB,
                label: copy.runsTab,
                badge: occurrences.data?.length,
                content: occurrences.isPending ? (
                  <SkeletonGroup className="co-dash__list-skeleton">
                    <Skeleton height={32} />
                    <Skeleton height={32} />
                  </SkeletonGroup>
                ) : occurrences.isLoadingError ? (
                  <ErrorState error={occurrences.error} onRetry={() => void occurrences.refetch()} compact />
                ) : (
                  <RunsTable runs={runs} />
                ),
              },
              {
                id: FLIPS_TAB,
                label: copy.flipsTab,
                badge: flips.data ? flipItems.length : undefined,
                content: flips.isPending ? (
                  <SkeletonGroup className="co-dash__list-skeleton">
                    <Skeleton height={32} />
                    <Skeleton height={32} />
                  </SkeletonGroup>
                ) : flips.isLoadingError ? (
                  <ErrorState error={flips.error} onRetry={() => void flips.refetch()} compact />
                ) : (
                  <>
                    <FlipsTable flips={flipItems} />
                    {flips.hasNextPage && (
                      <div className="co-list-foot">
                        <Button variant="secondary" size="sm" onClick={() => void flips.fetchNextPage()} loading={flips.isFetchingNextPage}>
                          {strings.common.loadMore}
                        </Button>
                      </div>
                    )}
                  </>
                ),
              },
            ]}
          />
        </section>
        <ScheduleCard job={data} />
      </div>

      <LatestMessage jobId={data.id} enabled={loaded} />

      <JobDrawer open={editOpen} job={data} onOpenChange={setEditOpen} />
      {actions.dialogs}
    </div>
  );
}
