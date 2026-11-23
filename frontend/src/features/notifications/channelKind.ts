/** The channel kinds, the notification statuses and the events: icon, tone
 *  and label per value. The badges show icon plus word, never colour alone. */
import { AlertTriangle, Bell, CircleCheck, CircleDashed, CircleX, Clock, FileText, Mail, MessageSquare, RotateCw, Undo2, Users, Webhook, type LucideIcon } from 'lucide-react';

import type { ChannelKind, ChannelStatus, NotificationEvent, NotificationStatus, RuleEvent } from '../../api/notifications';
import type { SeverityTone } from '../../components/ui/severity';
import { strings } from '../../strings';

export interface BadgeStyle {
  readonly tone: SeverityTone;
  readonly icon: LucideIcon;
}

export const KIND_ICONS: Record<ChannelKind, LucideIcon> = {
  email: Mail,
  slack: MessageSquare,
  teams: Users,
  webhook: Webhook,
};

export function kindLabel(kind: ChannelKind): string {
  return strings.channels.kinds[kind];
}

export const NOTIFICATION_STATUS_STYLES: Record<NotificationStatus, BadgeStyle> = {
  queued: { tone: 'info', icon: Clock },
  retrying: { tone: 'warning', icon: RotateCw },
  sent: { tone: 'success', icon: CircleCheck },
  failed: { tone: 'danger', icon: CircleX },
};

export function notificationStatusLabel(status: NotificationStatus): string {
  return strings.history.statuses[status];
}

/** The newest real delivery of a channel; null means nothing was sent yet. */
export const CHANNEL_STATUS_STYLES: Record<ChannelStatus | 'none', BadgeStyle> = {
  sent: { tone: 'success', icon: CircleCheck },
  failed: { tone: 'danger', icon: CircleX },
  none: { tone: 'muted', icon: CircleDashed },
};

export function channelStatusLabel(status: ChannelStatus | null): string {
  return status === 'sent' ? strings.channels.statusSent : status === 'failed' ? strings.channels.statusFailed : strings.channels.statusNone;
}

/** The event of a notification: the state the flip led to, the reminder or
 *  the digest. The icons follow the job state badges. */
export const EVENT_STYLES: Record<NotificationEvent, BadgeStyle> = {
  failing: { tone: 'danger', icon: CircleX },
  missed: { tone: 'danger', icon: CircleDashed },
  warning: { tone: 'warning', icon: AlertTriangle },
  recovered: { tone: 'success', icon: Undo2 },
  reminder: { tone: 'info', icon: Bell },
  digest: { tone: 'muted', icon: FileText },
};

export function eventLabel(event: NotificationEvent | RuleEvent): string {
  return strings.history.events[event];
}
