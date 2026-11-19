import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import '../features.css';

export interface PageHeaderProps {
  readonly icon: LucideIcon;
  readonly title: ReactNode;
  /** One line under the title: a lead or a count. */
  readonly lead?: ReactNode;
  /** Crumbs above the title (a back link). */
  readonly crumbs?: ReactNode;
  /** Badges next to the title. */
  readonly badges?: ReactNode;
  readonly actions?: ReactNode;
}

/** The page frame of every section: icon, title, lead, actions on the right. */
export function PageHeader({ icon: Icon, title, lead, crumbs, badges, actions }: PageHeaderProps) {
  return (
    <header className="co-page__header co-pagehead">
      <div className="co-pagehead__start">
        {crumbs && <div className="co-pagehead__crumbs">{crumbs}</div>}
        <div className="co-page__heading">
          <span className="co-page__icon" aria-hidden="true">
            <Icon size={22} strokeWidth={1.75} />
          </span>
          <h1 className="co-page__title co-pagehead__title">{title}</h1>
          {badges && <div className="co-pagehead__badges">{badges}</div>}
        </div>
        {lead && <p className="co-pagehead__lead">{lead}</p>}
      </div>
      {actions && <div className="co-pagehead__actions">{actions}</div>}
    </header>
  );
}
