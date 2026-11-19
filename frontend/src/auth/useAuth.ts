import { useContext } from 'react';

import { AuthContext, type AuthContextValue } from './context';

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth needs an AuthProvider above it');
  }
  return value;
}
