import * as RadixToast from '@radix-ui/react-toast';
import { CircleCheck, CircleX, Info, X } from 'lucide-react';
import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { strings } from '../../strings';
import { ToastContext, type ToastInput } from './toastContext';
import './ui.css';

interface ToastItem extends ToastInput {
  readonly id: number;
}

const ICONS = { success: CircleCheck, danger: CircleX, info: Info } as const;
const WORDS = { success: 'Done', danger: 'Failed', info: 'Note' } as const;

let nextId = 1;

export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [items, setItems] = useState<readonly ToastItem[]>([]);

  const toast = useCallback((input: ToastInput) => {
    const id = nextId;
    nextId += 1;
    setItems((current) => [...current, { ...input, id }]);
  }, []);

  const remove = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      <RadixToast.Provider swipeDirection="right" label="Notifications">
        {children}
        {items.map((item) => {
          const tone = item.tone ?? 'info';
          const Icon = ICONS[tone];
          return (
            <RadixToast.Root
              key={item.id}
              className={`co-toast co-toast--${tone}`}
              duration={item.duration ?? (tone === 'danger' ? 10_000 : 6_000)}
              onOpenChange={(open) => {
                if (!open) {
                  remove(item.id);
                }
              }}
            >
              <span className="co-toast__icon" aria-hidden="true">
                <Icon size={18} strokeWidth={2.25} />
              </span>
              <div className="co-toast__body">
                <RadixToast.Title className="co-toast__title">
                  <span className="co-toast__word">{WORDS[tone]}</span> {item.title}
                </RadixToast.Title>
                {item.description && (
                  <RadixToast.Description className="co-toast__description">{item.description}</RadixToast.Description>
                )}
              </div>
              <RadixToast.Close className="co-toast__close" aria-label={strings.toast.dismiss}>
                <X size={16} aria-hidden="true" />
              </RadixToast.Close>
            </RadixToast.Root>
          );
        })}
        <RadixToast.Viewport className="co-toast__viewport" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}
