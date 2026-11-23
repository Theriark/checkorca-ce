/**
 * The History tab: every notification, newest first, with its status (icon
 * plus word), what it is about (the job and client of the flip, the digest's
 * day), the channel, the attempts, the error sentence and the time that
 * matters now. Status and channel filter on the server; the cursor pages.
 * The list is quiet-polled while the first page is on screen.
 */
import { Link } from '@tanstack/react-router';
import { useEffect, useMemo, useState } from 'react';

import { NOTIFICATION_STATUSES, type NotificationOut, type NotificationStatus } from '../../api/notifications';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import type { DataTableColumn } from '../../components/ui/dataTableUtils';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { ChannelKindBadge, EventBadge, NotificationStatusBadge } from './NotificationBadges';
import { notificationStatusLabel } from './channelKind';
import { useChannelOptions, useNotificationList } from './queries';
import '../features.css';

export interface HistoryTabProps {
  /** The status filter from the address (?status=failed from the System page). */
  readonly status: string | null;
  /** Writes the status filter back to the address. */
  readonly onStatusChange?: (status: string | null) => void;
  /** Reports the number of loaded notifications for the tab badge. */
  readonly onCount?: (count: number | undefined) => void;
}

const ANY_STATUS = 'any';
const ANY_CHANNEL = 'any';

/** The time that matters now, with its word: sent, the next or last
 *  attempt, or when it was queued. */
function whenWords(notification: NotificationOut): { readonly label: string; readonly time: string } {
  const copy = strings.history;
  if (notification.status === 'sent' && notification.sent_at) {
    return { label: copy.sentAt, time: notification.sent_at };
  }
  if (notification.status === 'retrying' && notification.next_attempt_at) {
    return { label: copy.nextAttempt, time: notification.next_attempt_at };
  }
  if (notification.status === 'failed' && notification.last_attempt_at) {
    return { label: copy.lastAttempt, time: notification.last_attempt_at };
  }
  return { label: copy.queuedAt, time: notification.created_at };
}

function isStatus(value: string): value is NotificationStatus {
  return (NOTIFICATION_STATUSES as readonly string[]).includes(value);
}

/** What the notification is about: the job and client of the flip (the job
 *  name links to the job), the digest's day, or the reminder's flip. */
function AboutCell({ notification }: { readonly notification: NotificationOut }) {
  const copy = strings.history;
  if (notification.event === 'digest') {
    return <span className="co-cell-title">{fill(copy.digestOf, { day: notification.digest_day ?? '' })}</span>;
  }
  const job = notification.job_id ? (
    <Link className="co-cell-title__name" to="/jobs/$jobId" params={{ jobId: notification.job_id }}>
      {notification.job_name}
    </Link>
  ) : (
    <span className="co-cell-title__name">{notification.job_name ?? copy.jobGone}</span>
  );
  return (
    <span className="co-cell-title">
      {job}
      {notification.client_name && <span className="co-cell-title__sub">{notification.client_name}</span>}
    </span>
  );
}

export function HistoryTab({ status, onStatusChange, onCount }: HistoryTabProps) {
  const copy = strings.history;
  const [channelId, setChannelId] = useState<string>(ANY_CHANNEL);
  const statusFilter: NotificationStatus | null = status !== null && isStatus(status) ? status : null;
  const list = useNotificationList({ status: statusFilter, channel_id: channelId === ANY_CHANNEL ? null : channelId });
  const channels = useChannelOptions();

  const notifications = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const count = list.isSuccess ? notifications.length : undefined;
  useEffect(() => {
    onCount?.(count);
  }, [count, onCount]);

  const statusOptions = [{ value: ANY_STATUS, label: copy.anyStatus }, ...NOTIFICATION_STATUSES.map((item) => ({ value: item, label: notificationStatusLabel(item) }))];
  const channelOptions = [{ value: ANY_CHANNEL, label: copy.anyChannel }, ...(channels.data ?? []).map((item) => ({ value: item.id, label: item.label }))];

  const filterActive = statusFilter !== null || channelId !== ANY_CHANNEL;

  const columns: DataTableColumn<NotificationOut>[] = [
    {
      id: 'status',
      header: copy.columns.status,
      sortValue: (notification) => notification.status,
      cell: (notification) => (
        <span className="co-cell-state">
          <NotificationStatusBadge status={notification.status} size="sm" />
        </span>
      ),
    },
    {
      id: 'about',
      header: copy.columns.about,
      sortValue: (notification) => notification.job_name ?? notification.digest_day ?? '',
      cell: (notification) => (
        <span className="co-cell-state">
          <EventBadge event={notification.event} size="sm" />
          <AboutCell notification={notification} />
        </span>
      ),
    },
    {
      id: 'channel',
      header: copy.columns.channel,
      sortValue: (notification) => notification.channel_label,
      cell: (notification) => (
        <span className="co-cell-state">
          <ChannelKindBadge kind={notification.channel_kind} size="sm" />
          <span>{notification.channel_label}</span>
        </span>
      ),
    },
    {
      id: 'attempts',
      header: copy.columns.attempts,
      sortValue: (notification) => notification.attempts,
      align: 'end',
      cell: (notification) =>
        notification.attempts === 0 ? <span className="co-cell-muted">{copy.attemptNone}</span> : <span className="tabular">{notification.attempts === 1 ? copy.attemptOne : fill(copy.attempts, { count: notification.attempts })}</span>,
    },
    {
      id: 'error',
      header: copy.columns.error,
      sortValue: (notification) => notification.error ?? '',
      cell: (notification) => (notification.error ? <span className="co-cell-error">{notification.error}</span> : <span className="co-cell-muted">{copy.noError}</span>),
    },
    {
      id: 'when',
      header: copy.columns.when,
      sortValue: (notification) => whenWords(notification).time,
      cell: (notification) => {
        const when = whenWords(notification);
        return (
          <span className="co-cell-state">
            <span className="co-cell-state__note">{fill(when.label, { time: formatDateTime(when.time) })}</span>
          </span>
        );
      },
    },
  ];

  // The list is polled only while its first page alone is loaded (see
  // useNotificationList), so the note says so only then.
  const polling = (list.data?.pages.length ?? 0) <= 1;
  const noMatch = filterActive && notifications.length === 0;
  const emptyTitle = noMatch ? copy.noMatch : copy.emptyTitle;
  const emptyDescription = noMatch ? copy.noMatchLead : copy.emptyLead;

  // The count sentence is the tab's lead once the list is loaded, like the
  // other list pages; while it loads, the descriptive lead stays.
  const lead = list.isSuccess
    ? list.hasNextPage
      ? fill(copy.countMore, { count: notifications.length })
      : notifications.length === 1
        ? copy.countOne
        : fill(copy.count, { count: notifications.length })
    : copy.lead;

  return (
    <div className="co-notif__tab" data-testid="history-tab">
      <div className="co-notif__tabhead">
        <p className="co-notif__lead">{lead}</p>
      </div>
      <DataTable
        tableId="notifications"
        caption={copy.tableCaption}
        columns={columns}
        rows={notifications}
        getRowId={(notification) => notification.id}
        loading={list.isPending}
        error={list.isError ? list.error : undefined}
        onRetry={() => void list.refetch()}
        defaultSort={{ column: 'when', direction: 'desc' }}
        minWidth={860}
        toolbar={
          <>
            <Select
              label={copy.status}
              hideLabel
              size="sm"
              options={statusOptions}
              value={statusFilter ?? undefined}
              onValueChange={(value) => onStatusChange?.(value === ANY_STATUS ? null : value)}
              placeholder={copy.anyStatus}
            />
            <Select
              label={copy.channel}
              hideLabel
              size="sm"
              options={channelOptions}
              value={channelId === ANY_CHANNEL ? undefined : channelId}
              onValueChange={(value) => setChannelId(value)}
              placeholder={channels.isPending ? strings.states.loading : copy.anyChannel}
              disabled={channels.isPending || channelOptions.length <= 1}
            />
          </>
        }
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      />
      {list.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}
      {polling && (
        <p className="co-note">
          <span>{copy.polling}</span>
        </p>
      )}
    </div>
  );
}
