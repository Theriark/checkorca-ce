import * as RadixSelect from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { useId, type ReactNode } from 'react';

import './ui.css';

export interface SelectOption<V extends string = string> {
  readonly value: V;
  readonly label: ReactNode;
  readonly disabled?: boolean;
}

export interface SelectProps<V extends string = string> {
  readonly label: ReactNode;
  readonly options: readonly SelectOption<V>[];
  readonly value: V | undefined;
  readonly onValueChange: (value: V) => void;
  readonly placeholder?: string;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly disabled?: boolean;
  readonly size?: 'sm' | 'md';
  /** Hide the label visually (it stays the accessible name). */
  readonly hideLabel?: boolean;
  readonly id?: string;
  readonly className?: string;
}

/** A Radix select styled as a field: label, control, hint, error. */
export function Select<V extends string = string>({
  label,
  options,
  value,
  onValueChange,
  placeholder,
  hint,
  error,
  disabled,
  size = 'md',
  hideLabel = false,
  id,
  className,
}: SelectProps<V>) {
  const generated = useId();
  const triggerId = id ?? `select-${generated}`;
  const hintId = `${triggerId}-hint`;
  const errorId = `${triggerId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
  const classes = ['co-field'];
  if (error) {
    classes.push('co-field--invalid');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')}>
      <label className={hideLabel ? 'sr-only' : 'co-field__label'} htmlFor={triggerId}>
        {label}
      </label>
      <RadixSelect.Root value={value} onValueChange={onValueChange} disabled={disabled}>
        <RadixSelect.Trigger
          id={triggerId}
          className={`co-select co-select--${size}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
        >
          <RadixSelect.Value placeholder={placeholder} />
          <RadixSelect.Icon className="co-select__icon">
            <ChevronDown size={16} aria-hidden="true" />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal>
          <RadixSelect.Content className="co-select__content" position="popper" sideOffset={4}>
            <RadixSelect.Viewport className="co-select__viewport">
              {options.map((option) => (
                <RadixSelect.Item
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  className="co-select__item"
                >
                  <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                  <RadixSelect.ItemIndicator className="co-select__indicator">
                    <Check size={14} aria-hidden="true" />
                  </RadixSelect.ItemIndicator>
                </RadixSelect.Item>
              ))}
            </RadixSelect.Viewport>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
      {hint && (
        <p id={hintId} className="co-field__hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="co-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
