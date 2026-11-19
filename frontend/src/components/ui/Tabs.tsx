import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

import './ui.css';

export interface TabItem {
  readonly id: string;
  readonly label: ReactNode;
  readonly content: ReactNode;
  /** A count or short note after the label. */
  readonly badge?: ReactNode;
}

export interface TabsProps {
  readonly label: string;
  readonly items: readonly TabItem[];
  readonly value: string;
  readonly onValueChange: (id: string) => void;
  readonly className?: string;
}

/** The tabs pattern: a tablist with arrow, Home and End keys, one tabpanel. */
export function Tabs({ label, items, value, onValueChange, className }: TabsProps) {
  const baseId = useId();
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const active = items.find((item) => item.id === value) ?? items[0];

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === 'ArrowRight') {
      next = (index + 1) % items.length;
    } else if (event.key === 'ArrowLeft') {
      next = (index - 1 + items.length) % items.length;
    } else if (event.key === 'Home') {
      next = 0;
    } else if (event.key === 'End') {
      next = items.length - 1;
    }
    if (next === null) {
      return;
    }
    event.preventDefault();
    const target = items[next];
    if (target) {
      onValueChange(target.id);
      tabRefs.current.get(target.id)?.focus();
    }
  };

  const classes = ['co-tabs'];
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')}>
      <div role="tablist" aria-label={label} className="co-tabs__list">
        {items.map((item, index) => {
          const selected = item.id === active?.id;
          return (
            <button
              key={item.id}
              ref={(node) => {
                if (node) {
                  tabRefs.current.set(item.id, node);
                } else {
                  tabRefs.current.delete(item.id);
                }
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              className={selected ? 'co-tabs__tab co-tabs__tab--active' : 'co-tabs__tab'}
              onClick={() => onValueChange(item.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              <span>{item.label}</span>
              {item.badge !== undefined && <span className="co-tabs__badge tabular">{item.badge}</span>}
            </button>
          );
        })}
      </div>
      {active && (
        <div
          role="tabpanel"
          id={`${baseId}-panel-${active.id}`}
          aria-labelledby={`${baseId}-tab-${active.id}`}
          className="co-tabs__panel"
          tabIndex={0}
        >
          {active.content}
        </div>
      )}
    </div>
  );
}
