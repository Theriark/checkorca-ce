import { forwardRef, useId, type ReactNode, type TextareaHTMLAttributes } from 'react';

import './ui.css';

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  readonly label: ReactNode;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly optionalLabel?: string;
  readonly mono?: boolean;
  readonly id?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, optionalLabel, mono = false, id, className, rows = 3, ...rest },
  ref,
) {
  const generated = useId();
  const inputId = id ?? `textarea-${generated}`;
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
      <textarea
        ref={ref}
        id={inputId}
        rows={rows}
        className={mono ? 'co-input co-textarea mono' : 'co-input co-textarea'}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
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
