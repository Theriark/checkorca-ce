import { FileUp } from 'lucide-react';
import { useId, useRef, type ReactNode } from 'react';

import { strings } from '../../strings';
import { Button } from './Button';
import './ui.css';

export interface FileFieldProps {
  readonly label: ReactNode;
  readonly file: File | null;
  readonly onFileChange: (file: File | null) => void;
  readonly accept?: string;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly disabled?: boolean;
  readonly className?: string;
}

/** A file input drawn as a button plus the chosen name. The native input
 *  keeps the label, so the keyboard and screen readers reach it as a file
 *  control. */
export function FileField({ label, file, onFileChange, accept, hint, error, disabled, className }: FileFieldProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
  const classes = ['co-field', 'co-filefield'];
  if (error) {
    classes.push('co-field--invalid');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')}>
      <label className="co-field__label" htmlFor={id}>
        {label}
      </label>
      <div className="co-filefield__row">
        <input
          ref={inputRef}
          id={id}
          type="file"
          className="co-filefield__input"
          accept={accept}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
        <Button variant="secondary" iconStart={<FileUp size={16} />} disabled={disabled} onClick={() => inputRef.current?.click()} aria-hidden="true" tabIndex={-1}>
          {strings.importCsv.choose}
        </Button>
        <span className={file ? 'co-filefield__name' : 'co-filefield__name co-filefield__name--empty'} aria-live="polite">
          {file ? file.name : strings.importCsv.noFile}
        </span>
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
}
