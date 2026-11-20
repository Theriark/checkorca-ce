/**
 * /inboxes: every inbox with its kind badge, address or URL, sender rules
 * and last message time; a kind filter; create and edit in a drawer; copy
 * the address or URL, rotate a webhook token (shown once), upload an .eml
 * into an inbox, delete. Technicians and admins see the same screen.
 */
import { Link, useNavigate } from '@tanstack/react-router';
import { Copy, FileUp, Inbox, KeyRound, Mail, Pencil, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { INBOX_KINDS, type InboxCreated, type InboxKind, type InboxOut } from '../../api/inboxes';
import { ActionMenu, type ActionItem } from '../../components/ui/ActionMenu';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import { copyText } from '../../components/ui/copyText';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDate, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { UploadDialog } from '../messages/UploadDialog';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { InboxDrawer } from './InboxDrawer';
import { InboxReadyDialog, type InboxReveal } from './InboxReadyDialog';
import { KindBadge } from './KindBadge';
import { kindLabel } from './inboxKind';
import { useDeleteInbox, useInboxList, useRotateInboxToken } from './queries';
import '../features.css';

const ALL = 'all';

function RulesCell({ inbox }: { readonly inbox: InboxOut }) {
  const senders = inbox.sender_allowlist.length;
  return (
    <span className="co-cell-state">
      <span className={senders === 0 ? 'co-cell-muted' : undefined}>
        {senders === 0 ? strings.inboxes.anySender : senders === 1 ? strings.inboxes.senderOne : fill(strings.inboxes.senders, { count: senders })}
      </span>
      {inbox.require_auth_results && <span className="co-chip">{strings.inboxes.dkim}</span>}
    </span>
  );
}

export function InboxesPage() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [kind, setKind] = useState<string>(ALL);
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly inbox: InboxOut | null }>({ open: false, inbox: null });
  const [reveal, setReveal] = useState<InboxReveal | null>(null);
  const [rotateTarget, setRotateTarget] = useState<InboxOut | null>(null);
  const [rotateError, setRotateError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InboxOut | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ readonly open: boolean; readonly inboxId: string | null }>({ open: false, inboxId: null });
  const rotate = useRotateInboxToken();
  const remove = useDeleteInbox();

  const filters = useMemo(() => ({ kind: kind === ALL ? null : (kind as InboxKind) }), [kind]);
  const list = useInboxList(filters);
  const inboxes = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const filtered = kind !== ALL;

  const openEdit = (inbox: InboxOut) => setDrawer({ open: true, inbox });

  const copy = (value: string | null) => {
    if (!value) {
      return;
    }
    void copyText(value).then((ok) => toast(ok ? { tone: 'success', title: strings.common.copied } : { tone: 'danger', title: strings.common.copyFailed }));
  };

  const onCreated = (created: InboxCreated) => {
    if (created.kind === 'smtp' || created.kind === 'webhook') {
      setReveal({ kind: created.kind, label: created.label, address: created.address, ingestUrl: created.ingest_url, token: created.webhook_token, reason: 'created' });
    }
  };

  const confirmRotate = async () => {
    if (!rotateTarget) {
      return;
    }
    setRotateError(null);
    try {
      const result = await rotate.mutateAsync(rotateTarget.id);
      toast({ tone: 'success', title: strings.inboxes.rotated, description: rotateTarget.label });
      setReveal({ kind: 'webhook', label: rotateTarget.label, address: null, ingestUrl: rotateTarget.ingest_url, token: result.webhook_token, reason: 'rotated' });
      setRotateTarget(null);
    } catch (caught) {
      setRotateError(errorSentence(caught));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteError(null);
    try {
      await remove.mutateAsync(deleteTarget.id);
      toast({ tone: 'success', title: strings.inboxes.deleted, description: deleteTarget.label });
      setDeleteTarget(null);
    } catch (caught) {
      setDeleteError(errorSentence(caught));
    }
  };

  const menuFor = (inbox: InboxOut): readonly ActionItem[] => {
    const items: ActionItem[] = [{ id: 'edit', label: strings.inboxes.edit, icon: <Pencil size={16} />, onSelect: () => openEdit(inbox) }];
    if (inbox.kind === 'smtp') {
      items.push({ id: 'copy-address', label: strings.inboxes.copyAddress, icon: <Copy size={16} />, onSelect: () => copy(inbox.address) });
    }
    if (inbox.kind === 'smtp' || inbox.kind === 'webhook') {
      items.push({ id: 'copy-url', label: strings.inboxes.copyUrl, icon: <Copy size={16} />, onSelect: () => copy(inbox.ingest_url) });
    }
    if (inbox.kind === 'webhook') {
      items.push({
        id: 'rotate',
        label: strings.inboxes.rotateToken,
        icon: <KeyRound size={16} />,
        onSelect: () => {
          setRotateError(null);
          setRotateTarget(inbox);
        },
      });
    }
    items.push({ id: 'upload', label: strings.inboxes.upload, icon: <FileUp size={16} />, onSelect: () => setUpload({ open: true, inboxId: inbox.id }) });
    items.push({
      id: 'delete',
      label: strings.inboxes.delete,
      icon: <Trash2 size={16} />,
      tone: 'danger',
      separatorBefore: true,
      onSelect: () => {
        setDeleteError(null);
        setDeleteTarget(inbox);
      },
    });
    return items;
  };

  const columns: DataTableColumn<InboxOut>[] = [
    {
      id: 'label',
      header: strings.inboxes.columns.inbox,
      sortValue: (inbox) => inbox.label,
      cell: (inbox) => (
        <span className="co-cell-title">
          <span className="co-cell-title__name">{inbox.label}</span>
          {inbox.kind === 'smtp' && inbox.address && <span className="co-cell-title__sub mono">{inbox.address}</span>}
          {inbox.kind === 'webhook' && inbox.ingest_url && <span className="co-cell-title__sub mono co-cell-url">{inbox.ingest_url}</span>}
          {inbox.kind === 'imap' && inbox.imap && (
            <span className="co-cell-title__sub mono">
              {inbox.imap.host}:{inbox.imap.port} ({inbox.imap.username})
            </span>
          )}
          {inbox.kind === 'upload' && <span className="co-cell-title__sub">{strings.inboxes.noAddress}</span>}
        </span>
      ),
    },
    { id: 'kind', header: strings.inboxes.columns.kind, sortValue: (inbox) => inbox.kind, cell: (inbox) => <KindBadge kind={inbox.kind} size="sm" /> },
    { id: 'rules', header: strings.inboxes.columns.rules, sortValue: (inbox) => inbox.sender_allowlist.length, cell: (inbox) => <RulesCell inbox={inbox} /> },
    {
      id: 'last',
      header: strings.inboxes.columns.lastMessage,
      sortValue: (inbox) => inbox.last_message_at ?? '',
      numeric: true,
      cell: (inbox) => (inbox.last_message_at ? formatDateTime(inbox.last_message_at) : <span className="co-cell-muted">{strings.inboxes.noMessageYet}</span>),
    },
    { id: 'created', header: strings.inboxes.columns.created, sortValue: (inbox) => inbox.created_at, numeric: true, cell: (inbox) => formatDate(inbox.created_at) },
    {
      id: 'actions',
      header: <span className="sr-only">{strings.inboxes.columns.actions}</span>,
      align: 'end',
      width: '56px',
      cell: (inbox) => (
        <span className="co-cell-actions">
          <ActionMenu label={fill(strings.inboxes.actionsFor, { name: inbox.label })} items={menuFor(inbox)} />
        </span>
      ),
    },
  ];

  const count = inboxes.length;
  const lead = list.isSuccess
    ? list.hasNextPage
      ? fill(strings.inboxes.countMore, { count })
      : count === 1
        ? strings.inboxes.countOne
        : fill(strings.inboxes.count, { count })
    : strings.inboxes.lead;

  return (
    <div className="co-page">
      <PageHeader
        icon={Inbox}
        title={strings.inboxes.title}
        lead={lead}
        actions={
          <>
            <Link to="/messages" className="co-button co-button--secondary co-button--md">
              <span className="co-button__icon" aria-hidden="true">
                <Mail size={16} />
              </span>
              <span className="co-button__label">{strings.inboxes.messages}</span>
            </Link>
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, inbox: null })}>
              {strings.inboxes.new}
            </Button>
          </>
        }
      />

      <DataTable
        tableId="inboxes"
        caption={strings.inboxes.tableCaption}
        columns={columns}
        rows={inboxes}
        getRowId={(inbox) => inbox.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'created', direction: 'asc' }}
        onRowClick={openEdit}
        minWidth={760}
        emptyTitle={filtered ? strings.inboxes.noMatch : strings.inboxes.emptyTitle}
        emptyDescription={filtered ? strings.inboxes.noMatchLead : strings.inboxes.emptyLead}
        emptyAction={
          !filtered ? (
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, inbox: null })}>
              {strings.inboxes.new}
            </Button>
          ) : undefined
        }
        toolbar={
          <div className="co-filters">
            <Select
              className="co-filters__select"
              label={strings.inboxes.kind}
              hideLabel
              size="sm"
              value={kind}
              onValueChange={setKind}
              options={[{ value: ALL, label: strings.inboxes.anyKind }, ...INBOX_KINDS.map((item) => ({ value: item, label: kindLabel(item) }))]}
            />
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

      <InboxDrawer
        open={drawer.open}
        inbox={drawer.inbox}
        onOpenChange={(open) => setDrawer((current) => ({ ...current, open }))}
        onCreated={onCreated}
        onRotateToken={(inbox) => {
          setDrawer((current) => ({ ...current, open: false }));
          setRotateError(null);
          setRotateTarget(inbox);
        }}
      />
      <InboxReadyDialog reveal={reveal} onClose={() => setReveal(null)} />
      <ConfirmDialog
        open={rotateTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRotateTarget(null);
          }
        }}
        title={fill(strings.inboxes.rotateTitle, { name: rotateTarget?.label ?? '' })}
        description={strings.inboxes.rotateLead}
        confirmLabel={strings.inboxes.rotate}
        loadingLabel={strings.inboxes.rotating}
        busy={rotate.isPending}
        error={rotateError}
        onConfirm={() => void confirmRotate()}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        title={fill(strings.inboxes.deleteTitle, { name: deleteTarget?.label ?? '' })}
        description={strings.inboxes.deleteLead}
        confirmLabel={strings.common.delete}
        loadingLabel={strings.common.deleting}
        tone="danger"
        busy={remove.isPending}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
      />
      <UploadDialog
        open={upload.open}
        presetInboxId={upload.inboxId}
        onOpenChange={(open) => setUpload((current) => ({ ...current, open }))}
        onStored={(messageId) => void navigate({ to: '/messages/$messageId', params: { messageId } })}
      />
    </div>
  );
}
