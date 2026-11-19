import type { ReactNode } from 'react';

import { NightRibbonMark } from '../../ribbon/NightRibbonMark';
import './ui.css';

export interface EmptyStateProps {
  readonly title: ReactNode;
  readonly description?: ReactNode;
  /** What the person can do next (buttons or links). */
  readonly action?: ReactNode;
  /** A numbered checklist, for the first-run empty state. */
  readonly steps?: readonly ReactNode[];
  /** 'ribbon' shows the signature visual, 'mark' the orca mark, 'none' nothing. */
  readonly visual?: 'ribbon' | 'mark' | 'none';
  readonly compact?: boolean;
  readonly className?: string;
}

export function EmptyState({
  title,
  description,
  action,
  steps,
  visual = 'ribbon',
  compact = false,
  className,
}: EmptyStateProps) {
  const classes = ['co-empty'];
  if (compact) {
    classes.push('co-empty--compact');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')}>
      {visual === 'ribbon' && (
        <div className="co-empty__visual">
          <NightRibbonMark variant="empty" width={compact ? 160 : 240} />
        </div>
      )}
      {visual === 'mark' && (
        <img className="co-empty__mark" src="/brand/logo-mark-256x256.png" width={64} height={64} alt="" />
      )}
      <h3 className="co-empty__title">{title}</h3>
      {description && <p className="co-empty__description">{description}</p>}
      {steps && steps.length > 0 && (
        <ol className="co-empty__steps">
          {steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
      {action && <div className="co-empty__action">{action}</div>}
    </div>
  );
}
