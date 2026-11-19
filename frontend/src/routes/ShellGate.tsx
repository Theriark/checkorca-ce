import { Navigate, useRouterState } from '@tanstack/react-router';

import { useAuth } from '../auth/useAuth';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton, SkeletonGroup } from '../components/ui/Skeleton';
import { usePluginSlot } from '../plugins/slots';
import { AppShell } from '../shell/AppShell';
import { NotFoundPage } from './NotFoundPage';
import { isSectionPath } from './sections';
import './routes.css';

/** Renders the shell for a signed-in user, a boot skeleton while the session
 *  lookup runs, its error with a retry, or sends the visitor to /login. */
export function ShellGate() {
  const { status, user, error, refresh } = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const pluginRoutes = usePluginSlot('routes');
  const known = isSectionPath(pathname) || pluginRoutes.some((route) => route.path === pathname);
  if (!known) {
    // An unknown address is a 404 for everyone, never a sign-in prompt.
    return <NotFoundPage />;
  }
  if (status === 'loading') {
    return (
      <SkeletonGroup className="co-boot">
        <Skeleton height={64} radius="sm" />
        <Skeleton height={320} radius="md" />
      </SkeletonGroup>
    );
  }
  if (status === 'error') {
    return (
      <div className="co-boot">
        <ErrorState error={error} onRetry={refresh} />
      </div>
    );
  }
  if (status === 'anonymous' || !user) {
    return <Navigate to="/login" replace search={pathname !== '/' ? { redirect: pathname } : {}} />;
  }
  return <AppShell user={user} />;
}
