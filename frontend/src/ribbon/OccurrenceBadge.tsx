/** An occurrence state as a badge: icon plus word on the badge styles of
 *  components/ui, never colour alone. */
import type { OccurrenceState } from '../api/dashboard';
import { OCCURRENCE_STYLES, occurrenceLabel } from './occurrenceState';

export function OccurrenceBadge({ state, size = 'md', className }: { readonly state: OccurrenceState; readonly size?: 'sm' | 'md'; readonly className?: string }) {
  const { tone, icon: Icon } = OCCURRENCE_STYLES[state];
  const classes = ['co-badge', `co-badge--${tone}`, `co-badge--${size}`];
  if (className) {
    classes.push(className);
  }
  return (
    <span className={classes.join(' ')} data-occurrence={state}>
      <Icon className="co-badge__icon" aria-hidden="true" size={size === 'sm' ? 12 : 14} strokeWidth={2.25} />
      <span className="co-badge__label">{occurrenceLabel(state)}</span>
    </span>
  );
}
