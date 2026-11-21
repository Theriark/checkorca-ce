/** The status and source of a pack as badges: icon plus word, never colour
 *  alone. Unverified-synthetic carries the warning tone (built from synthetic
 *  samples only); verified the success tone. */
import { CircleCheck, FlaskConical, Package, PencilRuler } from 'lucide-react';

import type { PackSource, PackStatus } from '../../api/packs';
import { strings } from '../../strings';
import '../features.css';

export function PackStatusBadge({ status, size = 'md' }: { readonly status: PackStatus; readonly size?: 'sm' | 'md' }) {
  const verified = status === 'verified';
  const Icon = verified ? CircleCheck : FlaskConical;
  return (
    <span className={`co-badge co-badge--${verified ? 'success' : 'warning'} co-badge--${size}`} title={strings.parsers.statusHint[status]} data-status={status}>
      <Icon className="co-badge__icon" aria-hidden="true" size={size === 'sm' ? 12 : 14} strokeWidth={2.25} />
      <span className="co-badge__label">{strings.parsers.status[status]}</span>
    </span>
  );
}

export function PackSourceChip({ source, size = 'md' }: { readonly source: PackSource; readonly size?: 'sm' | 'md' }) {
  const Icon = source === 'builtin' ? Package : PencilRuler;
  return (
    <span className={`co-kind co-kind--${size}`} data-source={source}>
      <Icon className="co-kind__icon" size={size === 'sm' ? 12 : 14} aria-hidden="true" strokeWidth={2.25} />
      <span className="co-kind__label">{strings.parsers.source[source]}</span>
    </span>
  );
}
