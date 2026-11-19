import { useContext } from 'react';

import { ToastContext, type ToastContextValue } from './toastContext';

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error('useToast needs a ToastProvider above it');
  }
  return value;
}
