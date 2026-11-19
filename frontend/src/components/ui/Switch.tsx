import { useId, type ReactNode } from 'react';

import './ui.css';

export interface SwitchProps {
  readonly label: ReactNode;
  readonly checked: boolean;
  readonly onCheckedChange: (checked: boolean) => void;
  readonly disabled?: boolean;
  readonly id?: string;
  readonly className?: string;
}

/** A native checkbox with role switch, drawn as a toggle; the label is the
 *  accessible name and a click target. */
export function Switch({ label, checked, onCheckedChange, disabled, id, className }: SwitchProps) {
  const generated = useId();
  const inputId = id ?? `switch-${generated}`;
  const classes = ['co-switch'];
  if (className) {
    classes.push(className);
  }
  return (
    <label className={classes.join(' ')} htmlFor={inputId}>
      <input
        id={inputId}
        type="checkbox"
        role="switch"
        className="co-switch__input"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onCheckedChange(event.target.checked)}
      />
      <span className="co-switch__track" aria-hidden="true">
        <span className="co-switch__thumb" />
      </span>
      <span className="co-switch__label">{label}</span>
    </label>
  );
}
