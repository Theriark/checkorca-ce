/**
 * The Rules tab: every rule with its channel, its scope (all clients, one
 * client, one job) and its events, a channel filter, and a create or edit
 * drawer with the client and job pickers. A channel without a rule sends
 * nothing, and the empty state says so. Technicians read; admins change.
 */
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type { ChannelOut, RuleOut } from '../../api/notifications';
import { ActionMenu } from '../../components/ui/ActionMenu';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { errorSentence } from '../shared/errors';
import { ChannelKindBadge, EventChips } from './NotificationBadges';
import { RuleDrawer } from './RuleDrawer';
import { useChannelOptions, useDeleteRule, useRuleList } from './queries';
import '../features.css';

export interface RulesTabProps {
  readonly canEdit: boolean;
  /** Reports the number of loaded rules for the tab badge. */
  readonly onCount?: (count: number | undefined) => void;
  /** Opens the Channels tab, for the empty state without a channel. */
  readonly onGoChannels?: () => void;
}

/** The filter's "no channel chosen" value. */
const ANY_CHANNEL = 'any';

export function RulesTab({ canEdit, onCount, onGoChannels }: RulesTabProps) {
  const copy = strings.rules;
  const { toast } = useToast();
  const list = useRuleList();
  const channels = useChannelOptions();
  const remove = useDeleteRule();
  const [channelFilter, setChannelFilter] = useState<string>(ANY_CHANNEL);
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly rule: RuleOut | null }>({ open: false, rule: null });
  const [deleteTarget, setDeleteTarget] = useState<RuleOut | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const rules = useMemo(() => list.data ?? [], [list.data]);
  const channelItems = useMemo(() => channels.data ?? [], [channels.data]);
  const filtered = useMemo(() => (channelFilter === ANY_CHANNEL ? rules : rules.filter((rule) => rule.channel_id === channelFilter)), [rules, channelFilter]);
  const count = list.isSuccess ? filtered.length : undefined;
  // The badge follows the filtered list, so the filter answers on the tab too.
  useEffect(() => {
    onCount?.(count);
  }, [count, onCount]);

  const channelOf = (rule: RuleOut): ChannelOut | undefined => channelItems.find((item) => item.id === rule.channel_id);
  const filterOptions = [{ value: ANY_CHANNEL, label: copy.anyChannel }, ...channelItems.map((item) => ({ value: item.id, label: item.label }))];

  const openEdit = (rule: RuleOut) => {
    if (canEdit) {
      setDrawer({ open: true, rule });
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteError(null);
    try {
      await remove.mutateAsync(deleteTarget.id);
      toast({ tone: 'success', title: copy.deleted, description: channelOf(deleteTarget)?.label });
      setDeleteTarget(null);
    } catch (caught) {
      setDeleteError(errorSentence(caught));
    }
  };

  const scopeCell = (rule: RuleOut) => {
    if (rule.scope === 'all') {
      return <span>{copy.scopeAll}</span>;
    }
    if (rule.scope_name) {
      return <span className="co-cell-title"><span className="co-cell-title__name">{rule.scope_name}</span></span>;
    }
    return <span className="co-cell-muted">{fill(copy.scopeGone, { scope: rule.scope === 'client' ? copy.scopeClient.toLowerCase() : copy.scopeJob.toLowerCase() })}</span>;
  };

  const columns: DataTableColumn<RuleOut>[] = [
    {
      id: 'channel',
      header: copy.columns.channel,
      sortValue: (rule) => channelOf(rule)?.label ?? '',
      cell: (rule) => {
        const channel = channelOf(rule);
        return (
          <span className="co-cell-state">
            {channel ? (
              <>
                <ChannelKindBadge kind={channel.kind} size="sm" />
                <span>{channel.label}</span>
              </>
            ) : (
              <span className="co-cell-muted">{copy.channelGone}</span>
            )}
          </span>
        );
      },
    },
    { id: 'scope', header: copy.columns.scope, sortValue: (rule) => rule.scope, cell: scopeCell },
    { id: 'events', header: copy.columns.events, sortValue: (rule) => rule.events.join(' '), cell: (rule) => <EventChips events={rule.events} /> },
    { id: 'created', header: copy.columns.created, sortValue: (rule) => rule.created_at, cell: (rule) => <span className="tabular">{formatDateTime(rule.created_at)}</span> },
  ];
  if (canEdit) {
    columns.push({
      id: 'actions',
      header: <span className="sr-only">{copy.columns.actions}</span>,
      align: 'end',
      width: '120px',
      cell: (rule) => (
        <span className="co-cell-actions" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
          <ActionMenu
            label={fill(copy.actionsFor, { name: channelOf(rule)?.label ?? '' })}
            items={[
              { id: 'edit', label: copy.edit, icon: <Pencil size={16} />, onSelect: () => openEdit(rule) },
              {
                id: 'delete',
                label: copy.delete,
                icon: <Trash2 size={16} />,
                tone: 'danger',
                separatorBefore: true,
                onSelect: () => {
                  setDeleteError(null);
                  setDeleteTarget(rule);
                },
              },
            ]}
          />
        </span>
      ),
    });
  }

  const filterActive = channelFilter !== ANY_CHANNEL;
  // While the channels load the empty state cannot know yet whether a rule
  // could be made at all, so the table stays in its loading state.
  const noChannels = channels.isSuccess && channelItems.length === 0;
  const noRules = list.isSuccess && rules.length === 0;
  const noMatch = filterActive && filtered.length === 0;
  const emptyTitle = noMatch ? copy.noMatch : copy.emptyTitle;
  const emptyDescription = noMatch ? copy.noMatchLead : noChannels ? copy.emptyNoChannels : canEdit ? copy.emptyLead : copy.emptyLeadReadOnly;
  const emptyAction = noMatch ? (
    <Button variant="secondary" onClick={() => setChannelFilter(ANY_CHANNEL)}>
      {copy.anyChannel}
    </Button>
  ) : noChannels ? (
    canEdit && onGoChannels ? (
      <Button variant="secondary" onClick={onGoChannels}>
        {copy.toChannels}
      </Button>
    ) : undefined
  ) : noRules && canEdit ? (
    <Button variant="primary" iconStart={<Plus size={16} />} onClick={() => setDrawer({ open: true, rule: null })}>
      {copy.new}
    </Button>
  ) : undefined;

  // The count sentence is the tab's lead once the list is loaded, like the
  // other list pages; while it loads, the descriptive lead stays.
  const lead = list.isSuccess
    ? filtered.length === 1
      ? copy.countOne
      : fill(copy.count, { count: filtered.length })
    : copy.lead;

  return (
    <div className="co-notif__tab" data-testid="rules-tab">
      <div className="co-notif__tabhead">
        <p className="co-notif__lead">
          {lead}
          {!canEdit && <span className="co-notif__readonly"> {strings.notifications.readOnly}</span>}
        </p>
        {canEdit && (
          <Button variant="primary" iconStart={<Plus size={16} />} disabled={channelItems.length === 0} onClick={() => setDrawer({ open: true, rule: null })}>
            {copy.new}
          </Button>
        )}
      </div>
      <DataTable
        tableId="rules"
        caption={copy.tableCaption}
        columns={columns}
        rows={filtered}
        getRowId={(rule) => rule.id}
        loading={list.isPending || channels.isPending}
        error={list.isError ? list.error : channels.isError ? channels.error : undefined}
        onRetry={() => {
          void list.refetch();
          void channels.refetch();
        }}
        defaultSort={{ column: 'created', direction: 'desc' }}
        onRowClick={canEdit ? openEdit : undefined}
        minWidth={canEdit ? 760 : 640}
        toolbar={channelItems.length > 0 ? <Select label={copy.channel} hideLabel size="sm" options={filterOptions} value={channelFilter === ANY_CHANNEL ? undefined : channelFilter} onValueChange={(value) => setChannelFilter(value)} placeholder={copy.anyChannel} /> : undefined}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
        emptyAction={emptyAction}
      />
      <RuleDrawer
        open={drawer.open}
        rule={drawer.rule}
        channels={channelItems}
        presetChannelId={drawer.rule === null && filterActive ? channelFilter : null}
        onOpenChange={(open) => setDrawer((current) => ({ ...current, open }))}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        title={copy.deleteTitle}
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
