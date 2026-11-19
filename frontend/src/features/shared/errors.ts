import { ApiError, toApiError } from '../../api/client';
import { strings } from '../../strings';

/** The sentence to show for a failed request, with the request id for 5xx
 *  and network failures. */
export function errorSentence(error: unknown): string {
  const apiError = toApiError(error);
  if (apiError.isNetworkError) {
    return strings.login.offline;
  }
  const text = apiError.detail ?? apiError.title ?? strings.states.errorLead;
  const withId = apiError.status >= 500 && apiError.requestId ? `${text} (${strings.states.requestId} ${apiError.requestId})` : text;
  return withId;
}

export function isStatus(error: unknown, status: number): error is ApiError {
  return error instanceof ApiError && error.status === status;
}
