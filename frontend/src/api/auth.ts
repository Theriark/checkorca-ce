/** Typed calls of the auth routes (docs/auth.md, docs/openapi.json). */
import { api } from './client';
import type { components } from './schema';

export type SignedIn = components['schemas']['SignedIn'];
export type Me = components['schemas']['Me'];
export type SetupState = components['schemas']['SetupState'];
export type Credentials = components['schemas']['Credentials'];
export type NewAccount = components['schemas']['NewAccount'];
export type UserOut = components['schemas']['UserOut'];
export type Role = UserOut['role'];

export const authApi = {
  setupState: (signal?: AbortSignal) => api.get<SetupState>('/auth/setup-state', { signal }),
  me: (signal?: AbortSignal) => api.get<Me>('/auth/me', { signal }),
  login: (credentials: Credentials) => api.post<SignedIn>('/auth/login', { body: credentials }),
  firstRun: (account: NewAccount) => api.post<SignedIn>('/auth/first-run', { body: account }),
  logout: () => api.post<undefined>('/auth/logout'),
};
