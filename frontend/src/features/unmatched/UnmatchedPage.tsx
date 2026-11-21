/**
 * /unmatched: the results no job claimed, newest first, and a split view of
 * the one picked: the raw message text on the left (escaped text in
 * JetBrains Mono; React escapes every string, nothing renders HTML) and the
 * extracted fields on the right (job name, client hint, status, started,
 * finished, run id, details). Three ways out: Create job (prefilled from the
 * result), Assign to a job, and Suggest schedule (the job form with the
 * schedule editor filled from suggest-schedule).
 */
import { Link } from '@tanstack/react-router';
import { Briefcase, Link2, MailQuestion, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import type { MessageDetail, ResultOut } from '../../api/messages';
import type { UnmatchedOut } from '../../api/unmatched';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { ResultStatusBadge } from '../messages/MessageBadges';
import { PageHeader } from '../shared/PageHeader';
import { AssignDialog } from './AssignDialog';
import { CreateJobDrawer } from './CreateJobDrawer';
import { useRawMessage, useUnmatchedList } from './queries';
import '../features.css';

function Queue({ items, selectedId, onSelect }: { readonly items: readonly UnmatchedOut[]; readonly selectedId: string | null; readonly onSelect: (id: string) => void }) {
  const copy = strings.unmatched;
  return (
    <ul className="co-queue" aria-label={copy.queue}>
      {items.map((item) => {
        const selected = item.result_id === selectedId;
        return (
          <li key={item.result_id}>
            <button type="button" className={selected ? 'co-queue__item co-queue__item--selected' : 'co-queue__item'} aria-current={selected ? 'true' : undefined} onClick={() => onSelect(item.result_id)}>
              <span className="co-queue__head">
                <ResultStatusBadge status={item.status} size="sm" />
                <span className="co-queue__time tabular">{formatDateTime(item.received_at)}</span>
              </span>
              <span className="co-queue__name">{item.job_name ?? <span className="co-cell-muted">{copy.noJobName}</span>}</span>
              <span className="co-queue__client">{item.client_hint ?? <span className="co-cell-muted">{copy.noClientHint}</span>}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Value({ value }: { readonly value: string | null | undefined }) {
  return value ? <>{value}</> : <span className="co-summary__muted">{strings.common.none}</span>;
}

function Fields({ result, stored }: { readonly result: UnmatchedOut; readonly stored: ResultOut | null }) {
  const copy = strings.unmatched;
  const details = stored ? Object.entries(stored.details) : [];
  return (
    <dl className="co-kv co-fields">
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.job_name}</dt>
        <dd className="co-kv__value">
          <Value value={result.job_name} />
        </dd>
      </div>
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.client_hint}</dt>
        <dd className="co-kv__value">
          <Value value={result.client_hint} />
        </dd>
      </div>
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.status}</dt>
        <dd className="co-kv__value">
          <ResultStatusBadge status={result.status} />
        </dd>
      </div>
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.started_at}</dt>
        <dd className="co-kv__value tabular">
          <Value value={stored?.started_at ? formatDateTime(stored.started_at) : null} />
        </dd>
      </div>
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.finished_at}</dt>
        <dd className="co-kv__value tabular">
          <Value value={stored?.finished_at ? formatDateTime(stored.finished_at) : null} />
        </dd>
      </div>
      <div className="co-kv__item">
        <dt className="co-kv__label">{copy.field.run_id}</dt>
        <dd className="co-kv__value mono">
          <Value value={stored?.run_id ?? null} />
        </dd>
      </div>
      <div className="co-kv__item co-kv__item--wide">
        <dt className="co-kv__label">{copy.field.details}</dt>
        <dd className="co-kv__value">
          {details.length === 0 ? (
            <span className="co-summary__muted">{copy.noDetails}</span>
          ) : (
            <dl className="co-details">
              {details.map(([key, value]) => (
                <div key={key} className="co-details__row">
                  <dt className="co-details__key mono">{key}</dt>
                  <dd className="co-details__value">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </dd>
      </div>
    </dl>
  );
}

function RawPane({ result, message }: { readonly result: UnmatchedOut; readonly message: ReturnType<typeof useRawMessage> }) {
  const copy = strings.unmatched;
  if (!result.raw_message_id) {
    return <p className="co-split__note">{copy.rawMissing}</p>;
  }
  if (message.isPending) {
    return (
      <SkeletonGroup className="co-split__skeleton" label={copy.rawLoading}>
        <Skeleton height={14} width="60%" />
        <Skeleton height={14} width="90%" />
        <Skeleton height={14} width="75%" />
        <Skeleton height={14} width="85%" />
      </SkeletonGroup>
    );
  }
  if (message.isError) {
    if (message.error instanceof ApiError && message.error.status === 404) {
      return <p className="co-split__note">{copy.rawGone}</p>;
    }
    return <ErrorState error={message.error} onRetry={() => void message.refetch()} retrying={message.isFetching} compact />;
  }
  const detail: MessageDetail = message.data;
  return (
    <>
      <dl className="co-rawhead">
        <div className="co-rawhead__row">
          <dt>{strings.messages.detail.sender}</dt>
          <dd>{detail.sender || <span className="co-summary__muted">{strings.messages.noSender}</span>}</dd>
        </div>
        <div className="co-rawhead__row">
          <dt>{strings.messages.columns.subject}</dt>
          <dd>{detail.subject || <span className="co-summary__muted">{strings.messages.noSubject}</span>}</dd>
        </div>
      </dl>
      <div className="co-raw co-raw--split" tabIndex={0}>
        <pre className="co-raw__pre" data-testid="unmatched-raw">
          {detail.text.length > 0 ? detail.text : strings.messages.detail.bodyEmpty}
        </pre>
      </div>
      <Link to="/messages/$messageId" params={{ messageId: detail.id }} className="co-split__link">
        {copy.openMessage}
      </Link>
    </>
  );
}

export function UnmatchedPage() {
  const copy = strings.unmatched;
  const list = useUnmatchedList();
  const items = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Each dialog keeps the result it was opened for: once that result is bound
  // it leaves the queue and the view moves on, while the dialog still reads
  // the answer back for the result it worked on.
  const [assign, setAssign] = useState<{ readonly open: boolean; readonly result: UnmatchedOut | null }>({ open: false, result: null });
  const [create, setCreate] = useState<{ readonly open: boolean; readonly suggest: boolean; readonly result: UnmatchedOut | null }>({ open: false, suggest: false, result: null });
  // The pick, or the newest result once the queue is known (so a bound result
  // leaving the queue moves the view to the next one without a click).
  const selected = items.find((item) => item.result_id === selectedId) ?? items[0] ?? null;
  const message = useRawMessage(selected?.raw_message_id ?? null);
  const stored = useMemo(() => (selected && message.data ? (message.data.results.find((item) => item.id === selected.result_id) ?? null) : null), [message.data, selected]);

  const count = items.length;
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
        icon={MailQuestion}
        title={copy.title}
        lead={lead}
        actions={
          <Link to="/messages" className="co-button co-button--secondary co-button--md">
            <span className="co-button__label">{copy.messagesLink}</span>
          </Link>
        }
      />

      <div className="co-unmatched">
        <section className="co-card co-unmatched__queue" aria-labelledby="unmatched-queue-title">
          <div className="co-card__head">
            <h2 id="unmatched-queue-title" className="co-card__title">
              {copy.queue}
            </h2>
            <p className="co-card__lead">{copy.queueLead}</p>
          </div>
          {list.isPending ? (
            <SkeletonGroup className="co-queue co-queue--loading">
              <Skeleton height={72} radius="md" />
              <Skeleton height={72} radius="md" />
              <Skeleton height={72} radius="md" />
            </SkeletonGroup>
          ) : list.isError ? (
            <ErrorState error={list.error} onRetry={() => void list.refetch()} retrying={list.isFetching} compact />
          ) : items.length === 0 ? (
            <EmptyState compact visual="mark" title={copy.emptyTitle} description={copy.emptyLead} />
          ) : (
            <>
              <Queue items={items} selectedId={selected?.result_id ?? null} onSelect={setSelectedId} />
              {list.hasNextPage && (
                <div className="co-list-foot">
                  <Button variant="secondary" size="sm" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
                    {strings.common.loadMore}
                  </Button>
                </div>
              )}
            </>
          )}
        </section>

        <section className="co-card co-unmatched__detail" aria-labelledby="unmatched-detail-title">
          {selected ? (
            <>
              <div className="co-unmatched__head">
                <div className="co-card__head">
                  <h2 id="unmatched-detail-title" className="co-card__title">
                    {selected.job_name ?? copy.noJobName}
                  </h2>
                  <p className="co-card__lead">
                    {selected.client_hint ?? copy.noClientHint} · {copy.received} {formatDateTime(selected.received_at)}
                  </p>
                </div>
                <div className="co-unmatched__actions">
                  <Button variant="primary" iconStart={<Briefcase size={16} />} onClick={() => setCreate({ open: true, suggest: false, result: selected })}>
                    {copy.createJob}
                  </Button>
                  <Button variant="secondary" iconStart={<Link2 size={16} />} onClick={() => setAssign({ open: true, result: selected })}>
                    {copy.assign}
                  </Button>
                  <Button variant="secondary" iconStart={<Sparkles size={16} />} onClick={() => setCreate({ open: true, suggest: true, result: selected })}>
                    {copy.suggest}
                  </Button>
                </div>
              </div>
              <div className="co-split">
                <div className="co-split__pane co-split__pane--raw">
                  <h3 className="co-split__title">{copy.raw}</h3>
                  <p className="co-split__lead">{copy.rawLead}</p>
                  <RawPane result={selected} message={message} />
                </div>
                <div className="co-split__pane co-split__pane--fields">
                  <h3 className="co-split__title">{copy.fields}</h3>
                  <p className="co-split__lead">{copy.fieldsLead}</p>
                  <Fields result={selected} stored={stored} />
                </div>
              </div>
            </>
          ) : (
            <>
              <h2 id="unmatched-detail-title" className="sr-only">
                {copy.fields}
              </h2>
              <EmptyState compact visual="none" title={list.isSuccess && items.length === 0 ? copy.emptyTitle : copy.selectOne} description={list.isSuccess && items.length === 0 ? copy.emptyLead : undefined} />
            </>
          )}
        </section>
      </div>

      <AssignDialog open={assign.open} onOpenChange={(open) => setAssign((current) => ({ ...current, open }))} result={assign.result} />
      <CreateJobDrawer open={create.open} suggest={create.suggest} onOpenChange={(open) => setCreate((current) => ({ ...current, open }))} result={create.result} />
    </div>
  );
}
