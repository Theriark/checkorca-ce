import type { ReactNode } from 'react';

import { NightRibbonMark } from '../ribbon/NightRibbonMark';
import { Logo } from '../shell/Logo';
import { ThemeToggle } from '../shell/ThemeToggle';
import { APP_VERSION, strings } from '../strings';
import './routes.css';

/** The split layout of sign-in and first run: the Night Ribbon panel on the
 *  left from 1024 px, the stacked logo and the form in a card on the right. */
export function AuthFrame({ children, lead }: { readonly children: ReactNode; readonly lead: string }) {
  return (
    <div className="co-auth">
      <aside className="co-auth__panel" aria-hidden="true">
        <div className="co-auth__panel-inner">
          <NightRibbonMark variant="hero" width={360} className="co-auth__ribbon" />
          <p className="co-auth__panel-title">{strings.login.panelTitle}</p>
          <p className="co-auth__panel-text">{strings.login.panelText}</p>
        </div>
      </aside>
      <main className="co-auth__main">
        <div className="co-auth__toolbar">
          <ThemeToggle />
        </div>
        <section className="co-auth__card" aria-labelledby="auth-title">
          <Logo variant="stacked" width={168} className="co-auth__logo" />
          <p className="co-auth__lead">{lead}</p>
          {children}
        </section>
        <p className="co-auth__foot">
          <span>{strings.edition}</span>
          <span aria-hidden="true">·</span>
          <span className="tabular">{APP_VERSION}</span>
        </p>
      </main>
    </div>
  );
}
