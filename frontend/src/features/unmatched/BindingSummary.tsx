/**
 * What an assign or create-job did, in plain words (docs/parsers.md, The
 * binding): the job and client bound, whether the job's match key was set,
 * kept or replaced (with the old key), whether the client learned the hint
 * as an alias and if not why, and how many other results bound with it.
 */
import { Link } from '@tanstack/react-router';
import { CircleCheck, Info, KeyRound, Users } from 'lucide-react';

import type { Binding } from '../../api/unmatched';
import { Button } from '../../components/ui/Button';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import '../features.css';

export interface BindingSummaryProps {
  readonly binding: Binding;
  readonly jobName: string;
  readonly clientName: string;
  /** The result's names, for the sentences. */
  readonly resultJobName: string | null;
  readonly resultClientHint: string | null;
  /** Offered when the job kept another key; the old key is shown after. */
  readonly onReplaceKey?: () => void;
  readonly replacing?: boolean;
  /** The key that a later replacement overwrote (shown instead of the kept key). */
  readonly replacedOldKey?: string | null;
}

export function BindingSummary({ binding, jobName, clientName, resultJobName, resultClientHint, onReplaceKey, replacing = false, replacedOldKey = null }: BindingSummaryProps) {
  const copy = strings.unmatched;
  const hint = resultClientHint ?? '';
  const current = replacedOldKey !== null ? (resultJobName ?? '') : (binding.current_match_key ?? '');
  const oldKey = replacedOldKey ?? binding.replaced_match_key;
  let keyLine: React.ReactNode;
  if (oldKey !== null) {
    keyLine = fill(copy.keyReplaced, { old: oldKey, key: current });
  } else if (binding.match_key_set) {
    keyLine = fill(copy.keySet, { key: current });
  } else if (binding.current_match_key !== null) {
    keyLine = (
      <>
        <span>{fill(copy.keyUnchanged, { key: binding.current_match_key })}</span>
        {onReplaceKey && (
          <span className="co-binding__action">
            <Button size="sm" variant="secondary" iconStart={<KeyRound size={14} />} onClick={onReplaceKey} loading={replacing} loadingLabel={copy.replacingKey}>
              {copy.replaceKeyNow}
            </Button>
          </span>
        )}
      </>
    );
  } else {
    keyLine = copy.keyNone;
  }
  const aliasLine = binding.client_alias_added
    ? fill(copy.aliasAdded, { hint })
    : fill(copy.aliasReason[binding.reason ?? 'no_client_hint'], { hint });
  return (
    <div className="co-binding" role="status">
      <h3 className="co-binding__title">{copy.bindingTitle}</h3>
      <ul className="co-binding__list">
        <li className="co-binding__item co-binding__item--ok">
          <CircleCheck size={16} aria-hidden="true" />
          <span>
            {fill(copy.bindingBound, { job: jobName, client: clientName })}{' '}
            <Link to="/clients/$clientId" params={{ clientId: binding.client_id }}>
              {copy.openJob}
            </Link>
          </span>
        </li>
        <li className="co-binding__item">
          <KeyRound size={16} aria-hidden="true" />
          <span className="co-binding__text">{keyLine}</span>
        </li>
        <li className="co-binding__item">
          <Users size={16} aria-hidden="true" />
          <span>{aliasLine}</span>
        </li>
        {binding.also_bound > 0 && (
          <li className="co-binding__item">
            <Info size={16} aria-hidden="true" />
            <span>{binding.also_bound === 1 ? copy.alsoBoundOne : fill(copy.alsoBound, { count: binding.also_bound })}</span>
          </li>
        )}
      </ul>
    </div>
  );
}
