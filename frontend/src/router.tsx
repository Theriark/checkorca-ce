/**
 * Route tree (TanStack Router, code based).
 *
 *   /login, /first-run   public
 *   /                    the shell: morning check and the sections
 *   /_gallery            test build only (VITE_GALLERY=1)
 *   anything else        404
 *
 * The shell route renders nothing until the session lookup answers, then
 * sends an anonymous visitor to /login with the path to come back to.
 */
import { Outlet, createRootRoute, createRoute, createRouter, type RouterHistory } from '@tanstack/react-router';

import { FirstRunPage } from './routes/FirstRunPage';
import { GALLERY_ENABLED, GalleryRoute } from './routes/GalleryRoute';
import { LoginPage } from './routes/LoginPage';
import { NotFoundPage } from './routes/NotFoundPage';
import { PluginRouteOutlet } from './routes/PluginRouteOutlet';
import { SectionPage } from './routes/SectionPage';
import { ShellGate } from './routes/ShellGate';
import { sanitiseRedirect } from './routes/redirect';
import { SECTIONS } from './routes/sections';

export const GALLERY_PATH = '/_gallery';

const rootRoute = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: () => <NotFoundPage />,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => {
    const redirect = sanitiseRedirect(search.redirect);
    return redirect ? { redirect } : {};
  },
  component: LoginPage,
});

const firstRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/first-run',
  component: FirstRunPage,
});

const shellRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'shell',
  component: ShellGate,
});

const sectionRoutes = SECTIONS.map(({ path, key }) =>
  createRoute({
    getParentRoute: () => shellRoute,
    path,
    component: () => <SectionPage section={key} />,
  }),
);

// Plugin routes: one catch-all under the shell that resolves the exact path
// against the slot at render time, so the route tree stays static.
const pluginRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: '/$',
  component: PluginRouteOutlet,
});

// The gallery is loaded on demand and only in the test build (GalleryRoute).
const galleryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: GALLERY_PATH,
  component: GalleryRoute,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  firstRunRoute,
  shellRoute.addChildren([...sectionRoutes, pluginRoute]),
  ...(GALLERY_ENABLED ? [galleryRoute] : []),
]);

/** The app router; tests pass a memory history. */
export function createAppRouter(history?: RouterHistory) {
  return createRouter({
    routeTree,
    history,
    defaultPreload: false,
    scrollRestoration: true,
    notFoundMode: 'root',
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}
