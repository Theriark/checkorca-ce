/**
 * /messages/:id: the summary (inbox, sender, received, size, Message-ID,
 * parse state, client), the headers and the body as escaped text in
 * JetBrains Mono (React escapes every string; nothing here renders HTML,
 * no dangerouslySetInnerHTML, no iframe), and the results the parser read.
 * A long body scrolls inside its box; the 256 KB cut is the API's.
 */
import { Link, useParams } from '@tanstack/react-router';
import { ArrowLeft, Mail } from 'lucide-react';
import { useMemo } from 'react';

import { ApiError } from '../../api/client';
import type { MessageDetail } from '../../api/messages';
import { Alert } from '../../components/ui/Alert';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { useInboxOptions } from '../inboxes/queries';
import { KindBadge } from '../inboxes/KindBadge';
import { PageHeader } from '../shared/PageHeader';
import { ParseStateBadge, ResultStatusBadge } from './MessageBadges';
import { formatSize, useMessage } from './queries';
import '../features.css';

function Crumbs() {
  return (
    <Link to="/messages" className="co-pagehead__crumb">
      <ArrowLeft size={14} aria-hidden="true" />
      {strings.messages.detail.back}
    </Link>
  );
}

function Summary({ message }: { readonly message: MessageDetail }) {
  const inboxes = useInboxOptions();
  const clients = useClientOptions();
  const inbox = useMemo(() => (message.inbox_id ? inboxes.data?.find((item) => item.id === message.inbox_id) : undefined), [inboxes.data, message.inbox_id]);
  const client = useMemo(() => (message.client_id ? clients.data?.find((item) => item.id === message.client_id) : undefined), [clients.data, message.client_id]);
  return (
    <section className="co-card" aria-labelledby="message-summary-title">
      <h2 id="message-summary-title" className="co-card__title">
        {strings.messages.detail.summary}
      </h2>
      <dl className="co-kv co-kv--message">
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.inbox}</dt>
          <dd className="co-kv__value">
            {!message.inbox_id ? (
              <span className="co-summary__muted">{strings.messages.noInbox}</span>
            ) : inbox ? (
              <span className="co-cell-state">
                <KindBadge kind={inbox.kind} size="sm" />
                <span>{inbox.label}</span>
              </span>
            ) : (
              <span className="mono">{message.inbox_id}</span>
            )}
          </dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.sender}</dt>
          <dd className="co-kv__value">{message.sender || <span className="co-summary__muted">{strings.messages.noSender}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.received}</dt>
          <dd className="co-kv__value tabular">{formatDateTime(message.received_at)}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.size}</dt>
          <dd className="co-kv__value tabular">{formatSize(message.size)}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.state}</dt>
          <dd className="co-kv__value">
            <ParseStateBadge state={message.parse_state} />
          </dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{strings.messages.detail.client}</dt>
          <dd className="co-kv__value">
            {message.client_id ? (
              <Link to="/clients/$clientId" params={{ clientId: message.client_id }}>
                {client?.name ?? strings.messages.linkedClient}
              </Link>
            ) : (
              <span className="co-summary__muted">{strings.messages.notLinked}</span>
            )}
          </dd>
        </div>
        <div className="co-kv__item co-kv__item--wide">
          <dt className="co-kv__label">{strings.messages.detail.messageId}</dt>
          <dd className="co-kv__value mono co-kv__value--mono">{message.message_id ?? <span className="co-summary__muted">{strings.messages.detail.noMessageId}</span>}</dd>
        </div>
      </dl>
    </section>
  );
}

function Headers({ message }: { readonly message: MessageDetail }) {
  return (
    <section className="co-card" aria-labelledby="message-headers-title">
      <div className="co-card__head">
        <h2 id="message-headers-title" className="co-card__title">
          {strings.messages.detail.headers}
        </h2>
        <p className="co-card__lead">{strings.messages.detail.headersLead}</p>
      </div>
      <div className="co-raw co-raw--headers" tabIndex={0}>
        <dl className="co-headers">
          {message.headers.map((header, index) => (
            <div key={`${header.name}-${index}`} className="co-headers__row">
              <dt className="co-headers__name">{header.name}</dt>
              <dd className="co-headers__value">{header.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function Body({ message }: { readonly message: MessageDetail }) {
  return (
    <section className="co-card" aria-labelledby="message-body-title">
      <div className="co-card__head">
        <h2 id="message-body-title" className="co-card__title">
          {strings.messages.detail.body}
        </h2>
        <p className="co-card__lead">{strings.messages.detail.bodyLead}</p>
      </div>
      {message.text_truncated && <Alert tone="info">{strings.messages.detail.truncated}</Alert>}
      {message.text.length === 0 ? (
        <p className="co-summary__muted">{strings.messages.detail.bodyEmpty}</p>
      ) : (
        <div className="co-raw" tabIndex={0}>
          <pre className="co-raw__pre" data-testid="message-body">
            {message.text}
          </pre>
        </div>
      )}
    </section>
  );
}

function Results({ message }: { readonly message: MessageDetail }) {
  const detail = strings.messages.detail;
  return (
    <section className="co-card" aria-labelledby="message-results-title">
      <div className="co-card__head">
        <h2 id="message-results-title" className="co-card__title">
          {detail.results}
        </h2>
        <p className="co-card__lead">{detail.resultsLead}</p>
      </div>
      {message.results.length === 0 ? (
        <p className="co-summary__muted">{detail.noResults}</p>
      ) : (
        <div className="co-table__scroll" tabIndex={0}>
          <table className="co-import__table co-results">
            <caption className="sr-only">{detail.results}</caption>
            <thead>
              <tr>
                <th scope="col">{detail.resultStatus}</th>
                <th scope="col">{detail.resultJob}</th>
                <th scope="col">{detail.resultClient}</th>
                <th scope="col">{detail.resultRun}</th>
                <th scope="col">{detail.resultFinished}</th>
              </tr>
            </thead>
            <tbody>
              {message.results.map((result) => (
                <tr key={result.id}>
                  <td>
                    <ResultStatusBadge status={result.status} size="sm" />
                  </td>
                  <td>{result.job_name ?? (result.job_id ? <span className="mono">{result.job_id.slice(0, 8)}</span> : <span className="co-cell-muted">{detail.unbound}</span>)}</td>
                  <td>{result.client_hint ?? <span className="co-cell-muted">{strings.common.none}</span>}</td>
                  <td className="mono">{result.run_id ?? <span className="co-cell-muted">{strings.common.none}</span>}</td>
                  <td className="tabular">{result.finished_at ? formatDateTime(result.finished_at) : <span className="co-cell-muted">{strings.common.none}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function MessageDetailPage() {
  const { messageId } = useParams({ strict: false }) as { messageId: string };
  const query = useMessage(messageId);

  if (query.isPending) {
    return (
      <div className="co-page">
        <PageHeader icon={Mail} title={<Skeleton width={320} height={28} />} crumbs={<Crumbs />} />
        <SkeletonGroup className="co-stack">
          <Skeleton height={160} radius="md" />
          <Skeleton height={220} radius="md" />
          <Skeleton height={320} radius="md" />
        </SkeletonGroup>
      </div>
    );
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="co-page">
        <PageHeader icon={Mail} title={notFound ? strings.messages.detail.notFoundTitle : strings.messages.title} crumbs={<Crumbs />} />
        {notFound ? (
          <ErrorState title={strings.messages.detail.notFoundTitle} description={strings.messages.detail.notFoundLead} />
        ) : (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        )}
      </div>
    );
  }
  const message = query.data;
  return (
    <div className="co-page">
      <PageHeader
        icon={Mail}
        title={message.subject || strings.messages.noSubject}
        lead={message.sender ? `${message.sender}, ${formatDateTime(message.received_at)}` : formatDateTime(message.received_at)}
        crumbs={<Crumbs />}
        badges={<ParseStateBadge state={message.parse_state} />}
      />
      <Summary message={message} />
      <Body message={message} />
      <Headers message={message} />
      <Results message={message} />
    </div>
  );
}
