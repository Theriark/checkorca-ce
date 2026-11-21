/**
 * /messages: every stored message, newest first, with its sender, subject,
 * inbox, parse state and linked client; a duplicate flag when another loaded
 * message carries the same Message-ID; filters by inbox and parse state; the
 * .eml upload. A row opens the message.
 */
import { Link, useNavigate } from '@tanstack/react-router';
import { CopyCheck, FileUp, Mail } from 'lucide-react';
import { useMemo, useState } from 'react';

import { PARSE_STATES, type MessageOut, type ParseState } from '../../api/messages';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { useInboxOptions } from '../inboxes/queries';
import { KindBadge } from '../inboxes/KindBadge';
import { PageHeader } from '../shared/PageHeader';
import { UploadDialog } from './UploadDialog';
import { ParseStateBadge } from './MessageBadges';
import { parseStateLabel } from './messageState';
import { duplicateIds, useMessageList } from './queries';
import '../features.css';

const ALL = 'all';

export function MessagesPage() {
  const navigate = useNavigate();
  const [inboxId, setInboxId] = useState<string>(ALL);
  const [state, setState] = useState<string>(ALL);
  const [uploadOpen, setUploadOpen] = useState(false);
  const inboxes = useInboxOptions();
  const clients = useClientOptions();

  const filters = useMemo(
    () => ({ inbox_id: inboxId === ALL ? null : inboxId, parse_state: state === ALL ? null : (state as ParseState) }),
    [inboxId, state],
  );
  const list = useMessageList(filters);
  const messages = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const duplicates = useMemo(() => duplicateIds(messages), [messages]);
  const inboxById = useMemo(() => new Map((inboxes.data ?? []).map((inbox) => [inbox.id, inbox])), [inboxes.data]);
  const clientById = useMemo(() => new Map((clients.data ?? []).map((client) => [client.id, client])), [clients.data]);
  const filtered = inboxId !== ALL || state !== ALL;

  const open = (message: MessageOut) => void navigate({ to: '/messages/$messageId', params: { messageId: message.id } });

  const columns: DataTableColumn<MessageOut>[] = [
    {
      id: 'subject',
      header: strings.messages.columns.subject,
      sortValue: (message) => message.subject ?? '',
      cell: (message) => (
        <span className="co-cell-title">
          <span className="co-cell-title__name co-cell-subject">
            <Link to="/messages/$messageId" params={{ messageId: message.id }} className="co-cell-title__name" onClick={(event) => event.stopPropagation()}>
              {message.subject || strings.messages.noSubject}
            </Link>
            {duplicates.has(message.id) && (
              <span className="co-chip co-chip--icon" title={strings.messages.duplicateHint}>
                <CopyCheck size={12} aria-hidden="true" />
                {strings.messages.duplicate}
                <span className="sr-only">: {strings.messages.duplicateHint}</span>
              </span>
            )}
          </span>
          {message.message_id && <span className="co-cell-title__sub mono co-cell-url">{message.message_id}</span>}
        </span>
      ),
    },
    {
      id: 'sender',
      header: strings.messages.columns.sender,
      sortValue: (message) => message.sender ?? '',
      cell: (message) => (message.sender ? <span className="co-cell-sender">{message.sender}</span> : <span className="co-cell-muted">{strings.messages.noSender}</span>),
    },
    {
      id: 'inbox',
      header: strings.messages.columns.inbox,
      sortValue: (message) => (message.inbox_id ? (inboxById.get(message.inbox_id)?.label ?? message.inbox_id) : ''),
      cell: (message) => {
        const inbox = message.inbox_id ? inboxById.get(message.inbox_id) : undefined;
        if (!message.inbox_id) {
          return <span className="co-cell-muted">{strings.messages.noInbox}</span>;
        }
        return inbox ? (
          <span className="co-cell-state">
            <KindBadge kind={inbox.kind} size="sm" />
            <span>{inbox.label}</span>
          </span>
        ) : (
          <span className="mono co-cell-muted">{message.inbox_id.slice(0, 8)}</span>
        );
      },
    },
    {
      id: 'received',
      header: strings.messages.columns.received,
      sortValue: (message) => message.received_at,
      numeric: true,
      cell: (message) => formatDateTime(message.received_at),
    },
    { id: 'state', header: strings.messages.columns.state, sortValue: (message) => message.parse_state, cell: (message) => <ParseStateBadge state={message.parse_state} size="sm" /> },
    {
      id: 'client',
      header: strings.messages.columns.client,
      sortValue: (message) => (message.client_id ? (clientById.get(message.client_id)?.name ?? message.client_id) : ''),
      cell: (message) => {
        if (!message.client_id) {
          return <span className="co-cell-muted">{strings.messages.notLinked}</span>;
        }
        const client = clientById.get(message.client_id);
        return (
          <Link to="/clients/$clientId" params={{ clientId: message.client_id }} className="co-cell-title__name" onClick={(event) => event.stopPropagation()}>
            {client?.name ?? strings.messages.linkedClient}
          </Link>
        );
      },
    },
  ];

  const count = messages.length;
  const lead = list.isSuccess
    ? list.hasNextPage
      ? fill(strings.messages.countMore, { count })
      : count === 1
        ? strings.messages.countOne
        : fill(strings.messages.count, { count })
    : strings.messages.lead;
  const hasDuplicates = duplicates.size > 0;

  return (
    <div className="co-page">
      <PageHeader
        icon={Mail}
        title={strings.messages.title}
        lead={lead}
        crumbs={
          <Link to="/inboxes" className="co-pagehead__crumb">
            {strings.inboxes.title}
          </Link>
        }
        actions={
          <Button variant="primary" iconStart={<FileUp size={16} />} onClick={() => setUploadOpen(true)}>
            {strings.messages.upload}
          </Button>
        }
      />

      <DataTable
        tableId="messages"
        caption={strings.messages.tableCaption}
        columns={columns}
        rows={messages}
        getRowId={(message) => message.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'received', direction: 'desc' }}
        onRowClick={open}
        minWidth={880}
        emptyTitle={filtered ? strings.messages.noMatch : strings.messages.emptyTitle}
        emptyDescription={filtered ? strings.messages.noMatchLead : strings.messages.emptyLead}
        emptyAction={
          !filtered ? (
            <Button variant="primary" iconStart={<FileUp size={16} />} onClick={() => setUploadOpen(true)}>
              {strings.messages.upload}
            </Button>
          ) : undefined
        }
        toolbar={
          <div className="co-filters">
            <Select
              className="co-filters__select"
              label={strings.messages.inbox}
              hideLabel
              size="sm"
              value={inboxId}
              onValueChange={setInboxId}
              options={[{ value: ALL, label: strings.messages.anyInbox }, ...(inboxes.data ?? []).map((inbox) => ({ value: inbox.id, label: inbox.label }))]}
            />
            <Select
              className="co-filters__select"
              label={strings.messages.state}
              hideLabel
              size="sm"
              value={state}
              onValueChange={setState}
              options={[{ value: ALL, label: strings.messages.anyState }, ...PARSE_STATES.map((item) => ({ value: item, label: parseStateLabel(item) }))]}
            />
          </div>
        }
      />
      {hasDuplicates && (
        <p className="co-note">
          <CopyCheck size={14} aria-hidden="true" />
          <span>
            <strong>{strings.messages.duplicate}:</strong> {strings.messages.duplicateHint}
          </span>
        </p>
      )}
      {list.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onStored={(messageId) => void navigate({ to: '/messages/$messageId', params: { messageId } })} />
    </div>
  );
}
