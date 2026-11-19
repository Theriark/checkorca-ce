import { Link, useRouterState } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';

import { useAuth } from '../auth/useAuth';
import { NightRibbonMark } from '../ribbon/NightRibbonMark';
import { Logo } from '../shell/Logo';
import { ThemeToggle } from '../shell/ThemeToggle';
import { strings } from '../strings';
import './routes.css';

export function NotFoundPage({ reason }: { readonly reason?: string }) {
  const { status } = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const signedIn = status === 'signed-in';
  return (
    <main className="co-notfound">
      <div className="co-notfound__toolbar">
        <Logo variant="horizontal" width={168} />
        <ThemeToggle />
      </div>
      <div className="co-notfound__body">
        <NightRibbonMark variant="empty" width={280} />
        <p className="co-notfound__code tabular" aria-hidden="true">
          404
        </p>
        <h1 className="co-notfound__title">{strings.notFound.title}</h1>
        <p className="co-notfound__lead">{reason ?? strings.notFound.lead}</p>
        <p className="co-notfound__path">
          <span className="caps">{strings.notFound.pathLabel}</span>
          <code>{pathname}</code>
        </p>
        <Link to={signedIn ? '/' : '/login'} className="co-notfound__link">
          <ArrowLeft size={16} aria-hidden="true" />
          {signedIn ? strings.notFound.toHome : strings.notFound.toLogin}
        </Link>
      </div>
    </main>
  );
}
