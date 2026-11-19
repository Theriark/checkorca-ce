import { Loader2 } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

import './ui.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  /** Shows a spinner, keeps the width and disables the button. */
  readonly loading?: boolean;
  /** Text read while loading (defaults to the children). */
  readonly loadingLabel?: ReactNode;
  readonly iconStart?: ReactNode;
  readonly iconEnd?: ReactNode;
  /** Square button with an icon only; the label becomes the accessible name. */
  readonly iconOnly?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    loading = false,
    loadingLabel,
    iconStart,
    iconEnd,
    iconOnly = false,
    className,
    children,
    disabled,
    type = 'button',
    ...rest
  },
  ref,
) {
  const classes = ['co-button', `co-button--${variant}`, `co-button--${size}`];
  if (iconOnly) {
    classes.push('co-button--icon');
  }
  if (loading) {
    classes.push('co-button--loading');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <button
      ref={ref}
      type={type}
      className={classes.join(' ')}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <Loader2 className="co-button__spinner" aria-hidden="true" size={16} />
      ) : (
        iconStart && (
          <span className="co-button__icon" aria-hidden="true">
            {iconStart}
          </span>
        )
      )}
      <span className={iconOnly ? 'sr-only' : 'co-button__label'}>{loading && loadingLabel ? loadingLabel : children}</span>
      {!loading && iconEnd && (
        <span className="co-button__icon" aria-hidden="true">
          {iconEnd}
        </span>
      )}
    </button>
  );
});
