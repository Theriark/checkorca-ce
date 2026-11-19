import { createContext } from 'react';

import type { ApiError } from '../api/client';
import type { Credentials, Me, NewAccount } from '../api/auth';

export type AuthStatus = 'loading' | 'anonymous' | 'signed-in' | 'error';

export interface AuthContextValue {
  readonly status: AuthStatus;
  /** The signed-in user, when status is 'signed-in'. */
  readonly user: Me | null;
  /** Why the session lookup failed, when status is 'error'. */
  readonly error: ApiError | null;
  readonly signIn: (credentials: Credentials) => Promise<Me>;
  readonly createFirstAdmin: (account: NewAccount) => Promise<Me>;
  readonly signOut: () => Promise<void>;
  /** Re-run the session lookup (after an error). */
  readonly refresh: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export const ME_QUERY_KEY = ['auth', 'me'] as const;
