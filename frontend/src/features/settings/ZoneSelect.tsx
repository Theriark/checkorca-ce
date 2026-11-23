/**
 * The searchable IANA zone select: a text box with a listbox of the zones
 * the browser knows, filtered as the person types. Arrow keys move, Enter
 * takes, Escape closes; the mouse can click too. The full list is long
 * (hundreds of zones), so it shows the first matches and says how many more
 * are behind the typing.
 */
import { SearchX } from 'lucide-react';
import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import { fill } from '../../lib/format';
import { knownTimeZones } from '../../lib/timezones';
import { strings } from '../../strings';
import '../features.css';

/** How many zones the open list shows; the rest wait for narrower typing. */
const SHOWN = 8;

export interface ZoneSelectProps {
  readonly label: string;
  readonly value: string;
  readonly onValueChange: (zone: string) => void;
  readonly hint?: string;
  readonly error?: string;
  readonly disabled?: boolean;
}

export function ZoneSelect({ label, value, onValueChange, hint, error, disabled }: ZoneSelectProps) {
  const copy = strings.settings;
  const generated = useId();
  const inputId = `zone-${generated}`;
  const listId = `${inputId}-list`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const zones = useMemo(() => knownTimeZones(), []);

  const query = value.trim().toLowerCase();
  const matches = useMemo(() => zones.filter((zone) => zone.toLowerCase().includes(query)), [zones, query]);
  const shown = matches.slice(0, SHOWN);
  const more = matches.length - shown.length;

  const describedBy = [hint ? `${inputId}-hint` : null, error ? `${inputId}-error` : null].filter(Boolean).join(' ') || undefined;

  const select = (zone: string) => {
    onValueChange(zone);
    setOpen(false);
    inputRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!open || shown.length === 0) {
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((current) => Math.min(current + 1, shown.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current) => Math.max(current - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const zone = shown[active];
      if (zone) {
        select(zone);
      }
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className={error ? 'co-field co-field--invalid' : 'co-field'}>
      <label className="co-field__label" htmlFor={inputId}>
        {label}
      </label>
      <input
        ref={inputRef}
        id={inputId}
        className="co-input mono"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && shown[active] !== undefined ? `${listId}-opt-${active}` : undefined}
        aria-describedby={describedBy}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        value={value}
        onFocus={() => {
          setOpen(true);
          setActive(0);
        }}
        onBlur={() => setOpen(false)}
        onChange={(event) => {
          onValueChange(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
      />
      {open && (
        <div className="co-zoneselect" data-testid="zone-listbox">
          {shown.length === 0 ? (
            <p className="co-zoneselect__empty" id={`${listId}-empty`}>
              <SearchX size={14} aria-hidden="true" /> {copy.zoneNoMatch}
            </p>
          ) : (
            <ul id={listId} role="listbox" aria-label={copy.zoneResults} className="co-zoneselect__list">
              {shown.map((zone, index) => (
                <li key={zone} id={`${listId}-opt-${index}`} role="option" aria-selected={zone === value}>
                  <button
                    type="button"
                    className={index === active ? 'co-zoneselect__option co-zoneselect__option--active' : 'co-zoneselect__option'}
                    tabIndex={-1}
                    // The list must not steal the focus from the box: the
                    // click lands before the blur closes the list.
                    onMouseDown={(event) => {
                      event.preventDefault();
                      select(zone);
                    }}
                    onMouseEnter={() => setActive(index)}
                  >
                    {zone}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {more > 0 && (
            <p className="co-zoneselect__more">
              {fill(copy.zoneMore, { count: more })}
            </p>
          )}
        </div>
      )}
      {hint && (
        <p className="co-field__hint" id={`${inputId}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="co-field__error" id={`${inputId}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
