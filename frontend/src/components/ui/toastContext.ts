import { createContext, type ReactNode } from 'react';

export type ToastTone = 'success' | 'danger' | 'info';

export interface ToastInput {
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly tone?: ToastTone;
  /** Milliseconds before it leaves (default 6000; errors stay 10000). */
  readonly duration?: number;
}

export interface ToastContextValue {
  readonly toast: (input: ToastInput) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
