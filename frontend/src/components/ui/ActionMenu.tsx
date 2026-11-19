import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Ellipsis } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button } from './Button';
import './ui.css';

export interface ActionItem {
  readonly id: string;
  readonly label: ReactNode;
  readonly icon?: ReactNode;
  readonly onSelect: () => void;
  readonly disabled?: boolean;
  /** Red text for a destructive action. */
  readonly tone?: 'default' | 'danger';
  /** A separator above the item. */
  readonly separatorBefore?: boolean;
}

export interface ActionMenuProps {
  /** The accessible name of the trigger, for example "Actions for Veeam nightly". */
  readonly label: string;
  readonly items: readonly ActionItem[];
  readonly size?: 'sm' | 'md';
}

/** A row action menu on Radix DropdownMenu: one icon button, a list of
 *  actions, arrow keys and type-ahead for free. */
export function ActionMenu({ label, items, size = 'sm' }: ActionMenuProps) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size={size} iconOnly iconStart={<Ellipsis size={18} />} onClick={(event) => event.stopPropagation()}>
          {label}
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="co-actionmenu" align="end" sideOffset={4} onClick={(event) => event.stopPropagation()}>
          {items.map((item) => (
            <div key={item.id}>
              {item.separatorBefore && <DropdownMenu.Separator className="co-actionmenu__separator" />}
              <DropdownMenu.Item
                className={item.tone === 'danger' ? 'co-actionmenu__item co-actionmenu__item--danger' : 'co-actionmenu__item'}
                disabled={item.disabled}
                onSelect={item.onSelect}
              >
                {item.icon && (
                  <span className="co-actionmenu__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                )}
                {item.label}
              </DropdownMenu.Item>
            </div>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
