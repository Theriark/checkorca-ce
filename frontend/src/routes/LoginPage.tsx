import { Navigate, useNavigate } from '@tanstack/react-router';
import { Eye, EyeOff, ShieldAlert } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { toApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/ui/Button';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { Skeleton, SkeletonGroup } from '../components/ui/Skeleton';
import { strings } from '../strings';
import { AuthFrame } from './AuthFrame';
import { loginErrorMessage } from './authMessages';
import './routes.css';

export function LoginPage() {
  const { status, error: sessionError, refresh, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  if (status === 'signed-in') {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email.trim() || !password) {
      setFormError(strings.login.required);
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setRequestId(null);
    try {
      await signIn({ email: email.trim(), password });
      await navigate({ to: '/', replace: true });
    } catch (caught) {
      const apiError = toApiError(caught);
      setFormError(loginErrorMessage(apiError));
      setRequestId(apiError.status >= 500 || apiError.isNetworkError ? apiError.requestId : null);
      setSubmitting(false);
    }
  };

  return (
    <AuthFrame lead={strings.login.lead}>
      <h1 id="auth-title" className="co-auth__title">
        {strings.login.title}
      </h1>
      {status === 'loading' && (
        <SkeletonGroup className="co-auth__skeleton">
          <Skeleton height={40} radius="md" />
          <Skeleton height={40} radius="md" />
          <Skeleton height={40} radius="md" />
        </SkeletonGroup>
      )}
      {status === 'error' && <ErrorState error={sessionError} onRetry={refresh} compact />}
      {(status === 'anonymous' || status === 'error') && (
        <form className="co-auth__form" onSubmit={(event) => void onSubmit(event)} noValidate>
          {formError && (
            <div className="co-alert co-alert--danger" role="alert">
              <span className="co-alert__icon">
                <ShieldAlert size={18} aria-hidden="true" />
              </span>
              <div>
                <div>{formError}</div>
                {requestId && (
                  <div className="co-auth__request">
                    {strings.states.requestId}: <code>{requestId}</code>
                  </div>
                )}
              </div>
            </div>
          )}
          <Input
            label={strings.login.email}
            type="email"
            name="email"
            autoComplete="username"
            inputMode="email"
            spellCheck={false}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={submitting}
            required
          />
          <Input
            label={strings.login.password}
            type={showPassword ? 'text' : 'password'}
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            required
            trailing={
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                aria-pressed={showPassword}
                iconStart={showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                onClick={() => setShowPassword((value) => !value)}
              >
                {strings.login.showPassword}
              </Button>
            }
          />
          <Button
            type="submit"
            variant="primary"
            loading={submitting}
            loadingLabel={strings.login.submitting}
            className="co-auth__submit"
          >
            {strings.login.submit}
          </Button>
        </form>
      )}
    </AuthFrame>
  );
}
