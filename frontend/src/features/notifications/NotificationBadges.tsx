/** The badges of the notification pages: the channel kind (icon plus word,
 *  like the inbox kinds), a notification status, a channel's last delivery
 *  and an event. Never colour alone. */
import type { ChannelKind, ChannelStatus, NotificationEvent, NotificationStatus, RuleEvent } from '../../api/notifications';
import { CHANNEL_STATUS_STYLES, EVENT_STYLES, KIND_ICONS, NOTIFICATION_STATUS_STYLES, channelStatusLabel, eventLabel, kindLabel, notificationStatusLabel, type BadgeStyle } from './channelKind';
import '../features.css';

type Size = 'sm' | 'md';

export function ChannelKindBadge({ kind, size = 'md' }: { readonly kind: ChannelKind; readonly size?: Size }) {
  const Icon = KIND_ICONS[kind];
  return (
    <span className={`co-kind co-kind--${kind} co-kind--${size}`} data-kind={kind}>
      <Icon className="co-kind__icon" size={size === 'sm' ? 12 : 14} aria-hidden="true" strokeWidth={2.25} />
      <span className="co-kind__label">{kindLabel(kind)}</span>
    </span>
  );
}

function WordBadge({ style, label, size, testId, title }: { readonly style: BadgeStyle; readonly label: string; readonly size: Size; readonly testId?: string; readonly title?: string }) {
  const Icon = style.icon;
  return (
    <span className={`co-badge co-badge--${style.tone} co-badge--${size}`} data-testid={testId} title={title}>
      <Icon className="co-badge__icon" aria-hidden="true" size={size === 'sm' ? 12 : 14} strokeWidth={2.25} />
      <span className="co-badge__label">{label}</span>
    </span>
  );
}

export function NotificationStatusBadge({ status, size = 'md' }: { readonly status: NotificationStatus; readonly size?: Size }) {
  return <WordBadge style={NOTIFICATION_STATUS_STYLES[status]} label={notificationStatusLabel(status)} size={size} testId="notification-status" />;
}

export function ChannelStatusBadge({ status, size = 'md', title }: { readonly status: ChannelStatus | null; readonly size?: Size; readonly title?: string }) {
  return <WordBadge style={CHANNEL_STATUS_STYLES[status ?? 'none']} label={channelStatusLabel(status)} size={size} testId="channel-status" title={title} />;
}

export function EventBadge({ event, size = 'md' }: { readonly event: NotificationEvent; readonly size?: Size }) {
  return <WordBadge style={EVENT_STYLES[event]} label={eventLabel(event)} size={size} />;
}

/** The events of a rule as chips, in the API's order. */
export function EventChips({ events }: { readonly events: readonly RuleEvent[] }) {
  return (
    <ul className="co-chips co-events">
      {events.map((event) => {
        const Icon = EVENT_STYLES[event].icon;
        return (
          <li key={event} className="co-chip co-chip--icon co-events__chip" data-event={event}>
            <Icon size={12} aria-hidden="true" />
            {eventLabel(event)}
          </li>
        );
      })}
    </ul>
  );
}
