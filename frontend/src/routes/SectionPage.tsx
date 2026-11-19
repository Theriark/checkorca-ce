/**
 * The designed placeholder for a section whose phase is not built yet: the
 * page title, the phase that brings it, what it will hold, and a quiet
 * preview of its layout (skeleton blocks that do not animate). Never a blank
 * page.
 */
import { CalendarClock } from 'lucide-react';

import { strings } from '../strings';
import { NAV_ITEMS, type SectionKey } from '../shell/navigation';
import './routes.css';

export function SectionPage({ section }: { readonly section: SectionKey }) {
  const item = NAV_ITEMS.find((entry) => entry.key === section);
  const copy = strings.sections[section];
  const Icon = item?.icon ?? CalendarClock;
  return (
    <div className="co-page">
      <header className="co-page__header">
        <div className="co-page__heading">
          <span className="co-page__icon" aria-hidden="true">
            <Icon size={22} strokeWidth={1.75} />
          </span>
          <h1 className="co-page__title">{item?.label ?? section}</h1>
        </div>
        <span className="co-page__phase">
          <CalendarClock size={14} aria-hidden="true" />
          {strings.placeholder.arrives} {copy.phase}
        </span>
      </header>
      <div className="co-placeholder">
        <div className="co-placeholder__copy">
          <p className="co-placeholder__lead">{copy.lead}</p>
          <p className="caps">{strings.placeholder.lead}</p>
          <ul className="co-placeholder__list">
            {copy.items.map((entry) => (
              <li key={entry}>{entry}</li>
            ))}
          </ul>
        </div>
        <div className="co-placeholder__preview" aria-hidden="true">
          <div className="co-placeholder__row">
            <span className="co-placeholder__block co-placeholder__block--card" />
            <span className="co-placeholder__block co-placeholder__block--card" />
            <span className="co-placeholder__block co-placeholder__block--card" />
          </div>
          <span className="co-placeholder__block co-placeholder__block--bar" />
          <span className="co-placeholder__block co-placeholder__block--table" />
        </div>
      </div>
    </div>
  );
}
