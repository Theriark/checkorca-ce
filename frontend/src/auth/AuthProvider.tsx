/**
 * Session state for the whole app.
 *
 * On load it asks /auth/me once: 200 means signed in (and gives the CSRF token
 * for the client), 401 means anonymous, anything else is an error the shell
 * shows with a retry. Sign-in and first run store the CSRF token and replace
 * the cached user; sign-out clears both once the server has ended the session
 * (a failed logout keeps the user signed in and reports, so a shared
 * workstation is never left with a live server session behind a signed-out
 * screen).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, type ReactNode } from 'react';

import { authApi, type Credentials, type Me, type NewAccount, type SignedIn } from '../api/auth';
import { ApiError, setCsrfToken, toApiError } from '../api/client';
import { AuthContext, ME_QUERY_KEY, type AuthContextValue, type AuthStatus } from './context';

/** 401 is a normal answer (no session); it is cached as null, not thrown. */
async function fetchSession(signal: AbortSignal): Promise<Me | null> {
  try {
    const me = await authApi.me(signal);
    setCsrfToken(me.csrf_token);
    return me;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrfToken(null);
      return null;
    }
    throw error;
  }
}

function toMe(signedIn: SignedIn): Me {
  return {
    id: signedIn.user.id,
    email: signedIn.user.email,
    role: signedIn.user.role,
    csrf_token: signedIn.csrf_token,
  };
}

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => fetchSession(signal),
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    // Keep the client's token in step with the cached user (also after a
    // refetch that found the session gone).
    setCsrfToken(query.data?.csrf_token ?? null);
  }, [query.data]);

  const signIn = useCallback(
    async (credentials: Credentials) => {
      const me = toMe(await authApi.login(credentials));
      setCsrfToken(me.csrf_token);
      queryClient.setQueryData(ME_QUERY_KEY, me);
      return me;
    },
    [queryClient],
  );

  const createFirstAdmin = useCallback(
    async (account: NewAccount) => {
      const me = toMe(await authApi.firstRun(account));
      setCsrfToken(me.csrf_token);
      queryClient.setQueryData(ME_QUERY_KEY, me);
      return me;
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      // 401: the server session is already gone, so the local one goes too.
      // Anything else: keep the session and let the caller report it.
      if (!(error instanceof ApiError && error.status === 401)) {
        throw error;
      }
    }
    setCsrfToken(null);
    queryClient.setQueryData(ME_QUERY_KEY, null);
    queryClient.removeQueries({ predicate: (item) => item.queryKey[0] !== 'auth' });
  }, [queryClient]);

  const refresh = useCallback(() => {
    void query.refetch();
  }, [query]);

  const status: AuthStatus = query.isPending
    ? 'loading'
    : query.isError
      ? 'error'
      : query.data
        ? 'signed-in'
        : 'anonymous';

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: query.data ?? null,
      error: query.error ? toApiError(query.error) : null,
      signIn,
      createFirstAdmin,
      signOut,
      refresh,
    }),
    [status, query.data, query.error, signIn, createFirstAdmin, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
