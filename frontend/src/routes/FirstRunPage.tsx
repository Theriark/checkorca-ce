import { useQuery } from '@tanstack/react-query';
import { Navigate, useNavigate } from '@tanstack/react-router';
import { ShieldAlert } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { authApi } from '../api/auth';
import { toApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/ui/Button';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { Skeleton, SkeletonGroup } from '../components/ui/Skeleton';
import { strings } from '../strings';
import { AuthFrame } from './AuthFrame';
import { NotFoundPage } from './NotFoundPage';
import { firstRunValidation, loginErrorMessage } from './authMessages';
import './routes.css';

/**
 * /first-run: creates the first admin while no account exists. Once one does,
 * the server answers 404 and this page shows the 404 state (Development and
 * Stage are seeded before the port opens, so there it is always closed).
 */
export function FirstRunPage() {
  const { status, createFirstAdmin } = useAuth();
  const navigate = useNavigate();
  const setup = useQuery({
    queryKey: ['auth', 'setup-state'],
    queryFn: ({ signal }) => authApi.setupState(signal),
    retry: false,
  });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  if (status === 'signed-in') {
    return <Navigate to="/" replace />;
  }

  if (setup.isPending) {
    return (
      <AuthFrame lead={strings.firstRun.checking}>
        <h1 id="auth-title" className="co-auth__title">
          {strings.firstRun.title}
        </h1>
        <SkeletonGroup className="co-auth__skeleton" label={strings.firstRun.checking}>
          <Skeleton height={40} radius="md" />
          <Skeleton height={40} radius="md" />
          <Skeleton height={40} radius="md" />
          <Skeleton height={40} radius="md" />
        </SkeletonGroup>
      </AuthFrame>
    );
  }

  if (setup.isError) {
    return (
      <AuthFrame lead={strings.firstRun.checking}>
        <h1 id="auth-title" className="co-auth__title">
          {strings.firstRun.title}
        </h1>
        <ErrorState error={setup.error} onRetry={() => void setup.refetch()} retrying={setup.isFetching} compact />
      </AuthFrame>
    );
  }

  if (!setup.data.needs_first_run) {
    return <NotFoundPage reason={strings.firstRun.closed} />;
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const invalid = firstRunValidation(password, confirm);
    if (!email.trim()) {
      setFormError(strings.login.required);
      return;
    }
    if (invalid) {
      setFieldError(invalid);
      return;
    }
    setFieldError(null);
    setFormError(null);
    setSubmitting(true);
    try {
      await createFirstAdmin({ email: email.trim(), password });
      await navigate({ to: '/', replace: true });
    } catch (caught) {
      const apiError = toApiError(caught);
      if (apiError.status === 404) {
        await setup.refetch();
      }
      const emailMessage = apiError.fieldMessage('email');
      const passwordMessage = apiError.fieldMessage('password');
      setFieldError(passwordMessage ?? null);
      setFormError(emailMessage ?? loginErrorMessage(apiError));
      setSubmitting(false);
    }
  };

  return (
    <AuthFrame lead={strings.firstRun.lead}>
      <h1 id="auth-title" className="co-auth__title">
        {strings.firstRun.title}
      </h1>
      <form className="co-auth__form" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError && (
          <div className="co-alert co-alert--danger" role="alert">
            <span className="co-alert__icon">
              <ShieldAlert size={18} aria-hidden="true" />
            </span>
            <div>{formError}</div>
          </div>
        )}
        <Input
          label={strings.firstRun.email}
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
          label={strings.firstRun.password}
          type="password"
          name="new-password"
          autoComplete="new-password"
          hint={strings.firstRun.passwordHint}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={submitting}
          minLength={12}
          maxLength={128}
          required
        />
        <Input
          label={strings.firstRun.confirm}
          type="password"
          name="confirm-password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          error={fieldError}
          disabled={submitting}
          required
        />
        <Button
          type="submit"
          variant="primary"
          loading={submitting}
          loadingLabel={strings.firstRun.submitting}
          className="co-auth__submit"
        >
          {strings.firstRun.submit}
        </Button>
      </form>
    </AuthFrame>
  );
}
