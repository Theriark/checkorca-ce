import { SEVERITY_STYLES, severityLabel, type Severity } from './severity';
import './ui.css';

export type { Severity, SeverityTone } from './severity';

export interface SeverityBadgeProps {
  readonly severity: Severity;
  readonly size?: 'sm' | 'md';
  /** Extra text after the word, for example a count. */
  readonly detail?: string;
  readonly className?: string;
}

export function SeverityBadge({ severity, size = 'md', detail, className }: SeverityBadgeProps) {
  const { tone, icon: Icon } = SEVERITY_STYLES[severity];
  const classes = ['co-badge', `co-badge--${tone}`, `co-badge--${size}`];
  if (className) {
    classes.push(className);
  }
  return (
    <span className={classes.join(' ')} data-severity={severity}>
      <Icon className="co-badge__icon" aria-hidden="true" size={size === 'sm' ? 12 : 14} strokeWidth={2.25} />
      <span className="co-badge__label">{severityLabel(severity)}</span>
      {detail && <span className="co-badge__detail tabular">{detail}</span>}
    </span>
  );
}
