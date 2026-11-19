import { RotateCw, WifiOff, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { ApiError } from '../../api/client';
import { strings } from '../../strings';
import { Button } from './Button';
import './ui.css';

export interface ErrorStateProps {
  readonly title?: ReactNode;
  readonly description?: ReactNode;
  /** The error; its request id is shown for support. */
  readonly error?: unknown;
  readonly requestId?: string | null;
  readonly onRetry?: () => void;
  readonly retrying?: boolean;
  readonly compact?: boolean;
  readonly className?: string;
}

export function ErrorState({
  title,
  description,
  error,
  requestId,
  onRetry,
  retrying = false,
  compact = false,
  className,
}: ErrorStateProps) {
  const apiError = error instanceof ApiError ? error : null;
  const offline = apiError?.isNetworkError ?? false;
  const id = requestId ?? apiError?.requestId ?? null;
  const heading = title ?? (offline ? strings.states.offlineTitle : strings.states.errorTitle);
  const lead = description ?? (offline ? strings.login.offline : (apiError?.detail ?? strings.states.errorLead));
  const Icon = offline ? WifiOff : TriangleAlert;
  const classes = ['co-error'];
  if (compact) {
    classes.push('co-error--compact');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')} role="alert">
      <div className="co-error__icon" aria-hidden="true">
        <Icon size={compact ? 20 : 28} strokeWidth={2} />
      </div>
      <div className="co-error__body">
        <h3 className="co-error__title">{heading}</h3>
        <p className="co-error__description">{lead}</p>
        {id && (
          <p className="co-error__request">
            <span className="co-error__request-label">{strings.states.requestId}</span>{' '}
            <code className="co-error__request-id">{id}</code>
          </p>
        )}
        {onRetry && (
          <div className="co-error__action">
            <Button variant="secondary" size={compact ? 'sm' : 'md'} onClick={onRetry} loading={retrying} iconStart={<RotateCw size={16} />}>
              {strings.states.retry}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
