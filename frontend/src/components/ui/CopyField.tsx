import { Check, Copy } from 'lucide-react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

import { strings } from '../../strings';
import { Button } from './Button';
import { copyText } from './copyText';
import { useToast } from './useToast';
import './ui.css';

export interface CopyFieldProps {
  readonly label: ReactNode;
  /** The text to show and copy; null shows `unavailable` instead. */
  readonly value: string | null;
  readonly unavailable: ReactNode;
  readonly hint?: ReactNode;
  readonly className?: string;
}

/** A read-only mono field with a copy button; the value is selectable so a
 *  refused clipboard still leaves a way to copy. */
export function CopyField({ label, value, unavailable, hint, className }: CopyFieldProps) {
  const id = useId();
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
    },
    [],
  );

  const onCopy = async () => {
    if (value === null) {
      return;
    }
    const ok = await copyText(value);
    if (ok) {
      setCopied(true);
      toast({ tone: 'success', title: strings.common.copied });
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
      timer.current = window.setTimeout(() => setCopied(false), 2000);
    } else {
      inputRef.current?.select();
      toast({ tone: 'danger', title: strings.common.copyFailed });
    }
  };

  const classes = ['co-field', 'co-copyfield'];
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')}>
      <label className="co-field__label" htmlFor={id}>
        {label}
      </label>
      {value === null ? (
        <p id={id} className="co-copyfield__unavailable">
          {unavailable}
        </p>
      ) : (
        <div className="co-copyfield__row">
          <input
            ref={inputRef}
            id={id}
            className="co-input mono co-copyfield__input"
            value={value}
            readOnly
            onFocus={(event) => event.target.select()}
            aria-describedby={hint ? `${id}-hint` : undefined}
          />
          <Button variant="secondary" iconStart={copied ? <Check size={16} /> : <Copy size={16} />} onClick={() => void onCopy()}>
            {strings.common.copy}
          </Button>
        </div>
      )}
      {hint && (
        <p id={`${id}-hint`} className="co-field__hint">
          {hint}
        </p>
      )}
    </div>
  );
}
