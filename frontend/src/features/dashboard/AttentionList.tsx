/**
 * The needs-attention list of the morning check: silent first, then failed,
 * then warnings (the API orders them). Each row: the state as icon plus
 * word, the job and its client as links, the deadline, the last success,
 * and the actions: Acknowledge (shows the time once done; the API returns
 * no name), Pause, Open message when a mail decided the run.
 */
import { Link } from '@tanstack/react-router';
import { Check, Mail, Pause } from 'lucide-react';

import type { AttentionItem } from '../../api/dashboard';
import { Button } from '../../components/ui/Button';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import { useToast } from '../../components/ui/useToast';
import { fill, formatAgo, formatShortDateTime } from '../../lib/format';
import { strings } from '../../strings';
import type { JobActions } from '../jobs/useJobActions';
import { errorSentence } from '../shared/errors';
import { useAcknowledgeJob } from './queries';
import './dashboard.css';

export interface AttentionListProps {
  readonly items: readonly AttentionItem[];
  readonly actions: JobActions;
  readonly now?: Date;
}

export function AttentionList({ items, actions, now }: AttentionListProps) {
  const copy = strings.dashboard;
  const { toast } = useToast();
  const acknowledge = useAcknowledgeJob();
  const clock = now ?? new Date();

  const onAcknowledge = (item: AttentionItem) => {
    void acknowledge
      .mutateAsync(item.job_id)
      .then(() => toast({ tone: 'success', title: copy.acknowledgedToast, description: `${item.job_name}. ${copy.acknowledgedLead}` }))
      .catch((error: unknown) => toast({ tone: 'danger', title: copy.acknowledgeFailed, description: errorSentence(error) }));
  };

  return (
    <ol className="co-attn" aria-label={copy.attentionTitle}>
      {items.map((item) => {
        const busy = acknowledge.isPending && acknowledge.variables === item.job_id;
        return (
          <li key={item.job_id} className="co-attn__row" data-state={item.state} data-job={item.job_id}>
            <div className="co-attn__badge">
              <SeverityBadge severity={item.state} size="sm" />
            </div>
            <div className="co-attn__body">
              <div className="co-attn__names">
                <Link to="/jobs/$jobId" params={{ jobId: item.job_id }} className="co-attn__job">
                  {item.job_name}
                </Link>
                <Link to="/clients/$clientId" params={{ clientId: item.client_id }} className="co-attn__client">
                  {item.client_name}
                </Link>
              </div>
              <div className="co-attn__meta tabular">
                <span>{item.expected_by ? fill(copy.expectedBy, { time: formatShortDateTime(item.expected_by) }) : copy.noDeadline}</span>
                <span>{item.last_success_at ? fill(copy.lastSuccess, { time: formatAgo(item.last_success_at, clock) }) : copy.neverSucceeded}</span>
                {item.acknowledged_at && (
                  <span className="co-attn__ack">
                    <Check size={12} aria-hidden="true" />
                    {fill(copy.acknowledged, { time: formatShortDateTime(item.acknowledged_at) })}
                  </span>
                )}
              </div>
            </div>
            <div className="co-attn__actions">
              {!item.acknowledged_at && (
                <Button size="sm" variant="secondary" iconStart={<Check size={14} />} loading={busy} loadingLabel={copy.acknowledging} onClick={() => onAcknowledge(item)}>
                  {copy.acknowledge}
                </Button>
              )}
              <Button size="sm" variant="ghost" iconStart={<Pause size={14} />} onClick={() => actions.pause({ id: item.job_id, name: item.job_name })}>
                {copy.pause}
              </Button>
              {item.raw_message_id ? (
                <Link to="/messages/$messageId" params={{ messageId: item.raw_message_id }} className="co-button co-button--ghost co-button--sm">
                  <span className="co-button__icon" aria-hidden="true">
                    <Mail size={14} />
                  </span>
                  <span className="co-button__label">{copy.openMessage}</span>
                </Link>
              ) : (
                <span className="co-attn__nomessage" title={copy.noMessage}>
                  <Mail size={14} aria-hidden="true" />
                  <span className="sr-only">{copy.noMessage}</span>
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
