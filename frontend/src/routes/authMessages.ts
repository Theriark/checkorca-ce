import type { ApiError } from '../api/client';
import { strings } from '../strings';

/** The sentence for a failed sign-in, by the status the server gave. */
export function loginErrorMessage(error: ApiError): string {
  if (error.status === 401) {
    return strings.login.wrongCredentials;
  }
  if (error.status === 423) {
    return strings.login.locked;
  }
  if (error.status === 429) {
    return strings.login.tooMany;
  }
  if (error.isNetworkError) {
    return strings.login.offline;
  }
  return error.detail ?? strings.states.errorLead;
}

/** First-run validation before the request goes out; null when fine. */
export function firstRunValidation(password: string, confirm: string): string | null {
  if (password.length < 12) {
    return strings.firstRun.tooShort;
  }
  if (password !== confirm) {
    return strings.firstRun.mismatch;
  }
  return null;
}
