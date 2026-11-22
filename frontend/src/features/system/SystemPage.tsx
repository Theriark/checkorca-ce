/**
 * /system: the worker (heartbeat, holder, start), the evaluator lag, the
 * inboxes with their last message, the queues and the build (version,
 * revision, extension API level). Read from system/status, polled once a
 * minute by the shell's query. Technicians and admins see the same page.
 */
import { Activity, CircleCheck, OctagonAlert, Server } from 'lucide-react';

import type { SystemStatus } from '../../api/system';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { fill, formatDateTime } from '../../lib/format';
import { APP_VERSION, strings } from '../../strings';
import { KindBadge } from '../inboxes/KindBadge';
import { PageHeader } from '../shared/PageHeader';
import { useSystemStatus } from './queries';
import { staleMinutes } from './stale';
import '../features.css';
import '../dashboard/dashboard.css';

function ageWords(seconds: number | null): string {
  const copy = strings.system;
  if (seconds === null) {
    return copy.heartbeatNever;
  }
  return seconds < 120 ? fill(copy.heartbeatAge, { seconds: Math.max(0, Math.round(seconds)) }) : fill(copy.heartbeatAgeMinutes, { minutes: staleMinutes(seconds) });
}

function lagWords(seconds: number): string {
  const copy = strings.system;
  if (seconds <= 0) {
    return copy.lagNone;
  }
  return seconds < 120 ? fill(copy.lagSeconds, { seconds: Math.round(seconds) }) : fill(copy.lagMinutes, { minutes: Math.floor(seconds / 60) });
}

function WorkerCard({ status }: { readonly status: SystemStatus }) {
  const copy = strings.system;
  const worker = status.worker;
  return (
    <section className="co-card" aria-labelledby="sys-worker-title">
      <h2 id="sys-worker-title" className="co-card__title">
        {copy.workerTitle}
      </h2>
      <div className="co-sys__big">
        <span className={worker.stale ? 'co-badge co-badge--danger co-badge--md' : 'co-badge co-badge--success co-badge--md'} data-testid="worker-state">
          {worker.stale ? <OctagonAlert className="co-badge__icon" size={14} aria-hidden="true" strokeWidth={2.25} /> : <CircleCheck className="co-badge__icon" size={14} aria-hidden="true" strokeWidth={2.25} />}
          <span className="co-badge__label">{worker.stale ? copy.heartbeatStale : copy.heartbeatOk}</span>
        </span>
        <span className="co-sys__value tabular">{ageWords(worker.age_seconds)}</span>
      </div>
      <dl className="co-kv">
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.heartbeat}</dt>
          <dd className="co-kv__value tabular">{worker.heartbeat_at ? formatDateTime(worker.heartbeat_at) : <span className="co-summary__muted">{copy.heartbeatNever}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.holder}</dt>
          <dd className="co-kv__value">{worker.holder ? <span className="mono co-kv__value--mono">{worker.holder}</span> : <span className="co-summary__muted">{copy.noHolder}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.startedAt}</dt>
          <dd className="co-kv__value tabular">{worker.started_at ? formatDateTime(worker.started_at) : <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.evaluatorLag}</dt>
          <dd className="co-kv__value tabular" data-testid="evaluator-lag">
            {lagWords(status.evaluator_lag_seconds)}
          </dd>
        </div>
      </dl>
      <p className="co-card__lead">{copy.evaluatorLagLead}</p>
    </section>
  );
}

function InboxesCard({ status }: { readonly status: SystemStatus }) {
  const copy = strings.system;
  return (
    <section className="co-card" aria-labelledby="sys-inboxes-title">
      <div className="co-card__head">
        <h2 id="sys-inboxes-title" className="co-card__title">
          {copy.inboxesTitle}
        </h2>
        <p className="co-card__lead">{copy.inboxesLead}</p>
      </div>
      {status.inboxes.length === 0 ? (
        <p className="co-summary__muted">{copy.inboxesEmpty}</p>
      ) : (
        <ul className="co-sys__inboxes">
          {status.inboxes.map((inbox) => (
            <li key={inbox.id} className="co-sys__inbox">
              <span className="co-sys__inbox-name">
                <KindBadge kind={inbox.kind} size="sm" />
                <span>{inbox.label}</span>
              </span>
              <span className="co-sys__inbox-time tabular">{inbox.last_message_at ? formatDateTime(inbox.last_message_at) : copy.noMessageYet}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function QueuesCard({ status }: { readonly status: SystemStatus }) {
  const copy = strings.system;
  return (
    <section className="co-card" aria-labelledby="sys-queues-title">
      <h2 id="sys-queues-title" className="co-card__title">
        {copy.queuesTitle}
      </h2>
      <dl className="co-kv">
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.pendingMessages}</dt>
          <dd className="co-kv__value co-kv__value--big tabular">{status.queue.pending_messages}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.pendingNotifications}</dt>
          <dd className="co-kv__value co-kv__value--big tabular">{status.queue.pending_notifications}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.failedNotifications}</dt>
          <dd className="co-kv__value co-kv__value--big tabular">{status.queue.failed_notifications}</dd>
        </div>
      </dl>
      <p className="co-card__lead">{copy.notificationsNote}</p>
    </section>
  );
}

function BuildCard({ status }: { readonly status: SystemStatus }) {
  const copy = strings.system;
  return (
    <section className="co-card" aria-labelledby="sys-build-title">
      <h2 id="sys-build-title" className="co-card__title">
        {copy.buildTitle}
      </h2>
      <dl className="co-kv">
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.version}</dt>
          <dd className="co-kv__value tabular" data-testid="system-version">
            {status.version}
          </dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.revision}</dt>
          <dd className="co-kv__value" data-testid="system-revision">
            {status.revision ? <span className="mono co-kv__value--mono">{status.revision}</span> : <span className="co-summary__muted">{copy.noRevision}</span>}
          </dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.extensionApi}</dt>
          <dd className="co-kv__value tabular">{status.extension_api_level}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{copy.edition}</dt>
          <dd className="co-kv__value">
            {strings.edition} <span className="co-summary__muted tabular">{APP_VERSION}</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function SystemPage() {
  const copy = strings.system;
  const status = useSystemStatus();
  return (
    <div className="co-page">
      <PageHeader icon={Server} title={copy.title} lead={copy.lead} badges={<span className="co-chip co-chip--icon"><Activity size={12} aria-hidden="true" />{copy.refreshed}</span>} />
      {status.isPending ? (
        <SkeletonGroup className="co-sys__grid">
          <Skeleton height={220} radius="md" />
          <Skeleton height={220} radius="md" />
          <Skeleton height={180} radius="md" />
          <Skeleton height={180} radius="md" />
        </SkeletonGroup>
      ) : status.isError ? (
        <ErrorState error={status.error} onRetry={() => void status.refetch()} retrying={status.isFetching} />
      ) : (
        <div className="co-sys__grid">
          <WorkerCard status={status.data} />
          <InboxesCard status={status.data} />
          <QueuesCard status={status.data} />
          <BuildCard status={status.data} />
        </div>
      )}
    </div>
  );
}
