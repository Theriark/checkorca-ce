import { CircleCheck, Info, ShieldAlert, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import './ui.css';

export interface AlertProps {
  readonly tone?: 'danger' | 'warning' | 'info' | 'success';
  readonly title?: ReactNode;
  readonly children?: ReactNode;
  /** 'alert' announces at once (errors); 'status' politely (results). */
  readonly role?: 'alert' | 'status';
  readonly className?: string;
}

const ICONS = { danger: ShieldAlert, warning: TriangleAlert, info: Info, success: CircleCheck } as const;

/** An inline message with an icon and a coloured edge; never colour alone. */
export function Alert({ tone = 'info', title, children, role = tone === 'danger' ? 'alert' : 'status', className }: AlertProps) {
  const Icon = ICONS[tone];
  const classes = ['co-alert', `co-alert--${tone}`];
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')} role={role}>
      <span className="co-alert__icon">
        <Icon size={18} aria-hidden="true" />
      </span>
      <div className="co-alert__body">
        {title && <div className="co-alert__title">{title}</div>}
        {children}
      </div>
    </div>
  );
}
