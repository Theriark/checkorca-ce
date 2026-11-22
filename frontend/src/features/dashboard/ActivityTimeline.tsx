/**
 * The activity timeline: messages received, state changes and
 * configuration changes, newest first, with a kind filter and a Show more
 * button for the next cursor. Every entry says its kind in words and links
 * to what it is about when the API names a job, a message or a client.
 */
import { Link } from '@tanstack/react-router';
import { ArrowRightLeft, Bell, Mail, Settings2, type LucideIcon } from 'lucide-react';

import type { ActivityItem, ActivityKind } from '../../api/dashboard';
import { formatAgo, formatShortDateTime } from '../../lib/format';
import { strings } from '../../strings';
import './dashboard.css';

const ICONS: Record<ActivityKind, LucideIcon> = { ingest: Mail, flip: ArrowRightLeft, config: Settings2, notification: Bell };

function RefLink({ item }: { readonly item: ActivityItem }) {
  const label = strings.dashboard.activityOpen;
  if (!item.ref_id) {
    return null;
  }
  if (item.ref_kind === 'job') {
    return (
      <Link to="/jobs/$jobId" params={{ jobId: item.ref_id }} className="co-act__link">
        {label}
      </Link>
    );
  }
  if (item.ref_kind === 'message') {
    return (
      <Link to="/messages/$messageId" params={{ messageId: item.ref_id }} className="co-act__link">
        {label}
      </Link>
    );
  }
  if (item.ref_kind === 'client') {
    return (
      <Link to="/clients/$clientId" params={{ clientId: item.ref_id }} className="co-act__link">
        {label}
      </Link>
    );
  }
  return null;
}

export function ActivityTimeline({ items, now }: { readonly items: readonly ActivityItem[]; readonly now?: Date }) {
  const copy = strings.dashboard;
  const clock = now ?? new Date();
  return (
    <ol className="co-act" aria-label={copy.activityTitle}>
      {items.map((item) => {
        const Icon = ICONS[item.kind];
        return (
          <li key={item.id} className={`co-act__row co-act__row--${item.kind}`} data-kind={item.kind}>
            <span className="co-act__icon" aria-hidden="true">
              <Icon size={14} strokeWidth={2} />
            </span>
            <div className="co-act__body">
              <span className="co-act__summary">{item.summary}</span>
              <span className="co-act__meta">
                <span className="co-act__kind">{copy.activityKinds[item.kind]}</span>
                <time className="tabular" dateTime={item.at} title={formatShortDateTime(item.at)}>
                  {formatAgo(item.at, clock)}
                </time>
                <RefLink item={item} />
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
