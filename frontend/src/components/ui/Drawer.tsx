import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { strings } from '../../strings';
import { Button } from './Button';
import './ui.css';

export interface DrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: ReactNode;
  readonly description: ReactNode;
  readonly children?: ReactNode;
  /** Buttons, pinned to the bottom. */
  readonly footer?: ReactNode;
  readonly initialFocusRef?: React.RefObject<HTMLElement | null>;
  /** The id of the form the footer buttons submit (so Enter works too). */
  readonly className?: string;
}

const CONTROL_SELECTOR =
  '.co-drawer__body input:not([disabled]), .co-drawer__body select:not([disabled]), .co-drawer__body textarea:not([disabled]), .co-drawer__body button:not([disabled]), .co-drawer__body [tabindex]:not([tabindex="-1"])';

/** A side panel on Radix Dialog: right-anchored from 768 px, full width on a
 *  phone; focus trapped, Escape and overlay close, labelled by its title. */
export function Drawer({ open, onOpenChange, title, description, children, footer, initialFocusRef, className }: DrawerProps) {
  const classes = ['co-drawer'];
  if (className) {
    classes.push(className);
  }
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="co-dialog__overlay" />
        <RadixDialog.Content
          className={classes.join(' ')}
          onOpenAutoFocus={(event) => {
            const content = event.currentTarget as HTMLElement;
            const target = initialFocusRef?.current ?? content.querySelector<HTMLElement>(CONTROL_SELECTOR);
            if (target) {
              event.preventDefault();
              target.focus();
            }
          }}
        >
          <div className="co-drawer__header">
            <div className="co-drawer__heading">
              <RadixDialog.Title className="co-drawer__title">{title}</RadixDialog.Title>
              <RadixDialog.Description className="co-drawer__description">{description}</RadixDialog.Description>
            </div>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="sm" iconOnly iconStart={<X size={18} />}>
                {strings.dialog.close}
              </Button>
            </RadixDialog.Close>
          </div>
          <div className="co-drawer__body">{children}</div>
          {footer && <div className="co-drawer__footer">{footer}</div>}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
