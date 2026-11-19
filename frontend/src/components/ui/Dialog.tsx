import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { strings } from '../../strings';
import { Button } from './Button';
import './ui.css';

export interface DialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: ReactNode;
  /** One sentence under the title; announced as the dialog description. */
  readonly description?: ReactNode;
  readonly children?: ReactNode;
  /** Buttons, right-aligned. */
  readonly footer?: ReactNode;
  readonly size?: 'sm' | 'md' | 'lg';
  /** Red title band for a destructive confirm. */
  readonly tone?: 'default' | 'danger';
  /** Where focus goes on open (defaults to the first focusable element). */
  readonly initialFocusRef?: React.RefObject<HTMLElement | null>;
}

const CONTROL_SELECTOR =
  '.co-dialog__body input:not([disabled]), .co-dialog__body select:not([disabled]), .co-dialog__body textarea:not([disabled]), .co-dialog__body button:not([disabled]), .co-dialog__body [href], .co-dialog__body [tabindex]:not([tabindex="-1"]), .co-dialog__footer button:not([disabled])';

/** The first control in the body (then the footer), so focus starts on the
 *  work and not on the close button. */
function firstControl(content: HTMLElement): HTMLElement | null {
  return content.querySelector<HTMLElement>(CONTROL_SELECTOR);
}

/** A modal dialog on Radix: focus trap, Escape and overlay close, labelled
 *  by its title. The description is required by the product rule that every
 *  dialog says what it does in one sentence. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
  tone = 'default',
  initialFocusRef,
}: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="co-dialog__overlay" />
        <RadixDialog.Content
          className={`co-dialog co-dialog--${size} co-dialog--${tone}`}
          onOpenAutoFocus={(event) => {
            const target = initialFocusRef?.current ?? firstControl(event.currentTarget as HTMLElement);
            if (target) {
              event.preventDefault();
              target.focus();
            }
          }}
        >
          <div className="co-dialog__header">
            <RadixDialog.Title className="co-dialog__title">{title}</RadixDialog.Title>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="sm" iconOnly iconStart={<X size={18} />}>
                {strings.dialog.close}
              </Button>
            </RadixDialog.Close>
          </div>
          {description ? (
            <RadixDialog.Description className="co-dialog__description">{description}</RadixDialog.Description>
          ) : (
            <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
          )}
          {children && <div className="co-dialog__body">{children}</div>}
          {footer && <div className="co-dialog__footer">{footer}</div>}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export const DialogTrigger = RadixDialog.Trigger;
export const DialogClose = RadixDialog.Close;
