import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';

import './ui.css';

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'size'> {
  readonly label: ReactNode;
  /** Help text under the field. */
  readonly hint?: ReactNode;
  /** The validation message; sets aria-invalid and is announced. */
  readonly error?: ReactNode;
  /** Marks the label as optional instead of the field as required. */
  readonly optionalLabel?: string;
  /** A control at the end of the field, for example a show-password toggle. */
  readonly trailing?: ReactNode;
  readonly mono?: boolean;
  readonly id?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, optionalLabel, trailing, mono = false, id, className, required, ...rest },
  ref,
) {
  const generated = useId();
  const inputId = id ?? `input-${generated}`;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
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
      <label className="co-field__label" htmlFor={inputId}>
        {label}
        {optionalLabel && <span className="co-field__optional"> ({optionalLabel})</span>}
      </label>
      <div className="co-field__control">
        <input
          ref={ref}
          id={inputId}
          className={mono ? 'co-input mono' : 'co-input'}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          required={required}
          {...rest}
        />
        {trailing && <div className="co-field__trailing">{trailing}</div>}
      </div>
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
});
