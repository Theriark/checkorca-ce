/** The kind chip: icon plus word (never an icon or a colour alone). */
import type { InboxKind } from '../../api/inboxes';
import { KIND_ICONS, kindLabel } from './inboxKind';
import '../features.css';

export function KindBadge({ kind, size = 'md' }: { readonly kind: InboxKind; readonly size?: 'sm' | 'md' }) {
  const Icon = KIND_ICONS[kind];
  return (
    <span className={`co-kind co-kind--${kind} co-kind--${size}`} data-kind={kind}>
      <Icon className="co-kind__icon" size={size === 'sm' ? 12 : 14} aria-hidden="true" strokeWidth={2.25} />
      <span className="co-kind__label">{kindLabel(kind)}</span>
    </span>
  );
}
