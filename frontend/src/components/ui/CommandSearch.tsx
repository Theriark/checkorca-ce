/**
 * Command search: Ctrl K (or the header button) opens a dialog with one input
 * and a listbox of sections and actions. Typing filters; Up and Down move,
 * Enter runs, Escape closes. Built on the Dialog so focus is trapped and the
 * combobox pattern is announced.
 */
import * as RadixDialog from '@radix-ui/react-dialog';
import { CornerDownLeft, Search } from 'lucide-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';

import { strings } from '../../strings';
import { filterCommands } from './commandFilter';
import './ui.css';

export interface CommandItem {
  readonly id: string;
  readonly label: string;
  readonly group: 'sections' | 'actions';
  readonly icon?: ReactNode;
  /** Words that also match, for example a route path. */
  readonly keywords?: readonly string[];
  readonly run: () => void;
}

export interface CommandSearchProps {
  readonly items: readonly CommandItem[];
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

export function CommandSearch({ items, open, onOpenChange }: CommandSearchProps) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => filterCommands(items, query), [items, query]);

  useEffect(() => {
    if (!open) {
      setQuery('');
      setActive(0);
    }
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const run = useCallback(
    (item: CommandItem | undefined) => {
      if (!item) {
        return;
      }
      onOpenChange(false);
      item.run();
    },
    [onOpenChange],
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((current) => (results.length === 0 ? 0 : (current + 1) % results.length));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current) => (results.length === 0 ? 0 : (current - 1 + results.length) % results.length));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      run(results[active]);
    } else if (event.key === 'Home') {
      event.preventDefault();
      setActive(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      setActive(Math.max(results.length - 1, 0));
    }
  };

  const groups: readonly { readonly key: CommandItem['group']; readonly label: string }[] = [
    { key: 'sections', label: strings.search.sections },
    { key: 'actions', label: strings.search.actions },
  ];
  const activeId = results[active] ? `${listId}-${results[active].id}` : undefined;

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="co-dialog__overlay" />
        <RadixDialog.Content
          className="co-command"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
        >
          <RadixDialog.Title className="sr-only">{strings.search.label}</RadixDialog.Title>
          <RadixDialog.Description className="sr-only">{strings.search.hint}</RadixDialog.Description>
          <div className="co-command__field">
            <Search className="co-command__search-icon" size={18} aria-hidden="true" />
            <input
              ref={inputRef}
              className="co-command__input"
              type="text"
              role="combobox"
              aria-label={strings.search.label}
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={activeId}
              aria-autocomplete="list"
              autoComplete="off"
              spellCheck={false}
              placeholder={strings.search.placeholder}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onKeyDown}
            />
            <kbd className="co-command__kbd">Esc</kbd>
          </div>
          <div id={listId} role="listbox" aria-label={strings.search.label} className="co-command__list">
            {results.length === 0 && <p className="co-command__empty">{strings.search.noResults}</p>}
            {groups.map((group) => {
              const own = results.filter((item) => item.group === group.key);
              if (own.length === 0) {
                return null;
              }
              return (
                <div key={group.key} role="group" aria-label={group.label} className="co-command__group">
                  <div className="co-command__group-label caps" aria-hidden="true">
                    {group.label}
                  </div>
                  {own.map((item) => {
                    const index = results.indexOf(item);
                    const selected = index === active;
                    return (
                      <div
                        key={item.id}
                        id={`${listId}-${item.id}`}
                        role="option"
                        aria-selected={selected}
                        className={selected ? 'co-command__item co-command__item--active' : 'co-command__item'}
                        onMouseEnter={() => setActive(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => run(item)}
                      >
                        {item.icon && (
                          <span className="co-command__item-icon" aria-hidden="true">
                            {item.icon}
                          </span>
                        )}
                        <span className="co-command__item-label">{item.label}</span>
                        {selected && <CornerDownLeft className="co-command__enter" size={14} aria-hidden="true" />}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
          <p className="co-command__hint">{strings.search.hint}</p>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
