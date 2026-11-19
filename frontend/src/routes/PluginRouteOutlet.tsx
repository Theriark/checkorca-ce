import { useRouterState } from '@tanstack/react-router';

import { usePluginSlot } from '../plugins/slots';
import { NotFoundPage } from './NotFoundPage';

/** Resolves the exact path against the plugin route slot; 404 otherwise. */
export function PluginRouteOutlet() {
  const routes = usePluginSlot('routes');
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const match = routes.find((route) => route.path === pathname);
  if (!match) {
    return <NotFoundPage />;
  }
  const Component = match.component;
  return <Component />;
}
