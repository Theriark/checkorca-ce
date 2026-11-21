/**
 * Route tree (TanStack Router, code based).
 *
 *   /login, /first-run   public
 *   /                    the shell: morning check and the sections
 *   /clients/:id         a client under the shell
 *   /messages, /messages/:id   the messages of the inboxes, under the shell
 *   /parsers/packs/:id   a parser pack with its YAML editor and bench
 *   /parsers/bench       the test bench on its own
 *   /_gallery            test build only (VITE_GALLERY=1)
 *   anything else        404
 *
 * The shell route renders nothing until the session lookup answers, then
 * sends an anonymous visitor to /login with the path to come back to.
 */
import { Outlet, createRootRoute, createRoute, createRouter, type RouterHistory } from '@tanstack/react-router';

import { ClientDetailPage } from './features/clients/ClientDetailPage';
import { ClientsPage } from './features/clients/ClientsPage';
import { InboxesPage } from './features/inboxes/InboxesPage';
import { JobsPage } from './features/jobs/JobsPage';
import { MessageDetailPage } from './features/messages/MessageDetailPage';
import { MessagesPage } from './features/messages/MessagesPage';
import { BenchPage } from './features/parsers/BenchPage';
import { PackDetailPage } from './features/parsers/PackDetailPage';
import { ParsersPage } from './features/parsers/ParsersPage';
import { UnmatchedPage } from './features/unmatched/UnmatchedPage';
import { FirstRunPage } from './routes/FirstRunPage';
import { GALLERY_ENABLED, GalleryRoute } from './routes/GalleryRoute';
import { LoginPage } from './routes/LoginPage';
import { NotFoundPage } from './routes/NotFoundPage';
import { PluginRouteOutlet } from './routes/PluginRouteOutlet';
import { SectionPage } from './routes/SectionPage';
import { ShellGate } from './routes/ShellGate';
import { sanitiseRedirect } from './routes/redirect';
import { BENCH_PATH, CLIENT_DETAIL_PATH, MESSAGE_DETAIL_PATH, MESSAGES_PATH, PACK_DETAIL_PATH, SECTIONS } from './routes/sections';
import type { SectionKey } from './shell/navigation';

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

// The sections built so far; the others show their designed placeholder.
const BUILT: Partial<Record<SectionKey, () => React.JSX.Element>> = {
  clients: ClientsPage,
  jobs: JobsPage,
  unmatched: UnmatchedPage,
  inboxes: InboxesPage,
  parsers: ParsersPage,
};

const sectionRoutes = SECTIONS.map(({ path, key }) =>
  createRoute({
    getParentRoute: () => shellRoute,
    path,
    component: BUILT[key] ?? (() => <SectionPage section={key} />),
  }),
);

const clientDetailRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: CLIENT_DETAIL_PATH,
  component: ClientDetailPage,
});

const messagesRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: MESSAGES_PATH,
  component: MessagesPage,
});

const messageDetailRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: MESSAGE_DETAIL_PATH,
  component: MessageDetailPage,
});

const packDetailRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: PACK_DETAIL_PATH,
  component: PackDetailPage,
});

const benchRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: BENCH_PATH,
  component: BenchPage,
});

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
  shellRoute.addChildren([...sectionRoutes, clientDetailRoute, messagesRoute, messageDetailRoute, packDetailRoute, benchRoute, pluginRoute]),
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
