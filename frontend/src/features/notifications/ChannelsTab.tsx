/**
 * The Channels tab: every channel with its kind (icon plus word), label and
 * target, the enabled switch, the last real delivery as a badge, a test send
 * whose answer (ok and detail) is shown inline under the channel (a test
 * never changes last_status, so this is the only feedback), and a row menu
 * (Edit, Delete with a confirm). Technicians read; admins change.
 */
import { CircleCheck, CircleX, Pencil, Plus, Send, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { toApiError } from '../../api/client';
import type { ChannelOut, ChannelTestResult } from '../../api/notifications';
import { ActionMenu, type ActionItem } from '../../components/ui/ActionMenu';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Switch } from '../../components/ui/Switch';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { errorSentence } from '../shared/errors';
import { ChannelDrawer } from './ChannelDrawer';
import { ChannelKindBadge, ChannelStatusBadge } from './NotificationBadges';
import { recipientCount, targetWords } from './channelForm';
import { useChannelList, useDeleteChannel, useTestChannel, useUpdateChannel } from './queries';
import '../features.css';

export interface ChannelsTabProps {
  readonly canEdit: boolean;
  /** Reports the number of loaded channels for the tab badge. */
  readonly onCount?: (count: number | undefined) => void;
}

/** The answer of a test send, inline under the channel: a word with an
 *  icon, then the detail sentence as text. */
function TestNote({ channel, result, onDismiss }: { readonly channel: ChannelOut; readonly result: ChannelTestResult; readonly onDismiss: () => void }) {
  const copy = strings.channels;
  const Icon = result.ok ? CircleCheck : CircleX;
  return (
    <div className={result.ok ? 'co-testnote co-testnote--ok' : 'co-testnote co-testnote--failed'} role="status" aria-label={fill(copy.testResultFor, { name: channel.label })} data-testid="test-result">
      <Icon size={14} aria-hidden="true" className="co-testnote__icon" />
      <span className="co-testnote__body">
        <span className="co-testnote__word">{result.ok ? copy.testOk : copy.testFailed}</span>
        <span className="co-testnote__detail">{result.detail}</span>
      </span>
      <Button variant="ghost" size="sm" iconOnly iconStart={<X size={14} />} onClick={onDismiss}>
        {copy.dismissTest}
      </Button>
    </div>
  );
}

function TargetCell({ channel }: { readonly channel: ChannelOut }) {
  const copy = strings.channels;
  const target = targetWords(channel);
  if (!channel.available) {
    return <span className="co-chip co-chip--danger">{copy.unavailable}</span>;
  }
  if (channel.kind === 'email') {
    const count = recipientCount(channel);
    return (
      <>
        {target && <span className="co-cell-title__sub mono">{fill(copy.relay, { target })}</span>}
        <span className="co-cell-title__sub">{count === 1 ? copy.recipientOne : fill(copy.recipients, { count })}</span>
      </>
    );
  }
  return <span className="co-cell-title__sub">{target ? `${copy.urlSet} · ${fill(copy.urlHost, { host: target })}` : copy.urlUnknownHost}</span>;
}

export function ChannelsTab({ canEdit, onCount }: ChannelsTabProps) {
  const copy = strings.channels;
  const { toast } = useToast();
  const list = useChannelList();
  const update = useUpdateChannel();
  const remove = useDeleteChannel();
  const test = useTestChannel();
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly channel: ChannelOut | null }>({ open: false, channel: null });
  const [deleteTarget, setDeleteTarget] = useState<ChannelOut | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Readonly<Record<string, ChannelTestResult>>>({});

  const channels = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const count = list.isSuccess ? channels.length : undefined;
  // The badge of the tab follows the loaded list.
  useEffect(() => {
    onCount?.(count);
  }, [count, onCount]);

  const openEdit = (channel: ChannelOut) => {
    if (canEdit && channel.available) {
      setDrawer({ open: true, channel });
    }
  };

  const toggle = async (channel: ChannelOut, enabled: boolean) => {
    try {
      await update.mutateAsync({ channelId: channel.id, body: { enabled } });
      toast({ tone: 'success', title: enabled ? copy.enabledToast : copy.disabledToast, description: channel.label });
    } catch (caught) {
      toast({ tone: 'danger', title: copy.toggleFailed, description: errorSentence(caught) });
    }
  };

  const sendTest = async (channel: ChannelOut) => {
    setTesting(channel.id);
    setResults((current) => {
      const next = { ...current };
      delete next[channel.id];
      return next;
    });
    try {
      const result = await test.mutateAsync(channel.id);
      setResults((current) => ({ ...current, [channel.id]: result }));
    } catch (caught) {
      // A 422 Target refused (a URL the guard now refuses) or any other
      // refusal reads as a failed test with its sentence, never the URL.
      const error = toApiError(caught);
      setResults((current) => ({ ...current, [channel.id]: { ok: false, detail: errorSentence(error) } }));
    } finally {
      setTesting(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteError(null);
    try {
      await remove.mutateAsync(deleteTarget.id);
      toast({ tone: 'success', title: copy.deleted, description: deleteTarget.label });
      setDeleteTarget(null);
    } catch (caught) {
      setDeleteError(errorSentence(caught));
    }
  };

  const menuFor = (channel: ChannelOut): readonly ActionItem[] => [
    { id: 'edit', label: copy.edit, icon: <Pencil size={16} />, disabled: !channel.available, onSelect: () => openEdit(channel) },
    {
      id: 'delete',
      label: copy.delete,
      icon: <Trash2 size={16} />,
      tone: 'danger',
      separatorBefore: true,
      onSelect: () => {
        setDeleteError(null);
        setDeleteTarget(channel);
      },
    },
  ];

  const columns: DataTableColumn<ChannelOut>[] = [
    {
      id: 'label',
      header: copy.columns.channel,
      sortValue: (channel) => channel.label,
      cell: (channel) => {
        const result = results[channel.id];
        return (
          <span className="co-cell-title">
            <span className="co-cell-title__name">{channel.label}</span>
            <TargetCell channel={channel} />
            {result && (
              <TestNote
                channel={channel}
                result={result}
                onDismiss={() =>
                  setResults((current) => {
                    const next = { ...current };
                    delete next[channel.id];
                    return next;
                  })
                }
              />
            )}
          </span>
        );
      },
    },
    { id: 'kind', header: copy.columns.kind, sortValue: (channel) => channel.kind, cell: (channel) => <ChannelKindBadge kind={channel.kind} size="sm" /> },
    {
      id: 'enabled',
      header: copy.columns.enabled,
      sortValue: (channel) => (channel.enabled ? 1 : 0),
      cell: (channel) =>
        canEdit && channel.available ? (
          <span className="co-cell-switch" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
            <Switch label={<span className="sr-only">{fill(copy.enabledFor, { name: channel.label })}</span>} checked={channel.enabled} disabled={update.isPending} onCheckedChange={(value) => void toggle(channel, value)} />
          </span>
        ) : (
          <span className={channel.enabled ? undefined : 'co-cell-muted'}>{channel.enabled ? strings.common.yes : strings.common.no}</span>
        ),
    },
    {
      id: 'status',
      header: copy.columns.lastDelivery,
      sortValue: (channel) => channel.last_status_at ?? '',
      cell: (channel) => (
        <span className="co-cell-state">
          <ChannelStatusBadge status={channel.last_status} size="sm" title={channel.last_status === 'failed' && channel.last_error ? channel.last_error : undefined} />
          {channel.last_status_at && <span className="co-cell-state__note tabular">{formatDateTime(channel.last_status_at)}</span>}
          {channel.last_status === 'failed' && channel.last_error && (
            <span className="co-cell-state__note co-cell-error">
              <span className="sr-only">{copy.lastError}: </span>
              {channel.last_error}
            </span>
          )}
        </span>
      ),
    },
  ];
  if (canEdit) {
    columns.push({
      id: 'actions',
      header: <span className="sr-only">{copy.columns.actions}</span>,
      align: 'end',
      width: '180px',
      cell: (channel) => (
        <span className="co-cell-actions" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
          <Button size="sm" variant="secondary" iconStart={<Send size={14} />} disabled={!channel.available || testing !== null} loading={testing === channel.id} loadingLabel={copy.testing} onClick={() => void sendTest(channel)}>
            {copy.test}
          </Button>
          <ActionMenu label={fill(copy.actionsFor, { name: channel.label })} items={menuFor(channel)} />
        </span>
      ),
    });
  }

  // The count sentence is the tab's lead once the list is loaded, like the
  // other list pages; while it loads, the descriptive lead stays.
  const lead = list.isSuccess
    ? list.hasNextPage
      ? fill(copy.countMore, { count: channels.length })
      : channels.length === 1
        ? copy.countOne
        : fill(copy.count, { count: channels.length })
    : copy.lead;

  return (
    <div className="co-stack co-notif__tab" data-testid="channels-tab">
      <div className="co-notif__tabhead">
        <p className="co-notif__lead">
          {lead}
          {!canEdit && <span className="co-notif__readonly"> {strings.notifications.readOnly}</span>}
        </p>
        {canEdit && (
          <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, channel: null })}>
            {copy.new}
          </Button>
        )}
      </div>
      <DataTable
        tableId="channels"
        caption={copy.tableCaption}
        columns={columns}
        rows={channels}
        getRowId={(channel) => channel.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'label', direction: 'asc' }}
        onRowClick={canEdit ? openEdit : undefined}
        minWidth={canEdit ? 820 : 640}
        emptyTitle={copy.emptyTitle}
        emptyDescription={canEdit ? copy.emptyLead : copy.emptyLeadReadOnly}
        emptyAction={
          canEdit ? (
            <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, channel: null })}>
              {copy.new}
            </Button>
          ) : undefined
        }
      />
      {list.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}
      <p className="co-note">
        <Send size={14} aria-hidden="true" />
        <span>{copy.testLead}</span>
      </p>

      <ChannelDrawer open={drawer.open} channel={drawer.channel} onOpenChange={(open) => setDrawer((current) => ({ ...current, open }))} />
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        title={fill(copy.deleteTitle, { name: deleteTarget?.label ?? '' })}
        description={copy.deleteLead}
        confirmLabel={strings.common.delete}
        loadingLabel={strings.common.deleting}
        tone="danger"
        busy={remove.isPending}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
