import { APP_VERSION, PRODUCT_NAME, strings } from './strings';

const BRAND = '/brand';

export function App() {
  return (
    <div className="shell">
      <header className="shell-header">
        <picture>
          <source
            media="(prefers-color-scheme: dark)"
            srcSet={`${BRAND}/logo-horizontal-dark-600x200.png 1x, ${BRAND}/logo-horizontal-dark-1200x400.png 2x`}
          />
          <img
            className="shell-logo"
            src={`${BRAND}/logo-horizontal-600x200.png`}
            srcSet={`${BRAND}/logo-horizontal-600x200.png 1x, ${BRAND}/logo-horizontal-1200x400.png 2x`}
            alt={PRODUCT_NAME}
            width={216}
            height={72}
          />
        </picture>
        <span className="shell-edition">{strings.edition}</span>
      </header>
      <main className="shell-main">
        <section className="shell-card" aria-labelledby="shell-title">
          <h1 id="shell-title">{strings.title}</h1>
          <p className="shell-lead">{strings.lead}</p>
          <p>{strings.shellNote}</p>
          <dl className="shell-facts">
            <div>
              <dt>{strings.versionLabel}</dt>
              <dd>{APP_VERSION}</dd>
            </div>
            <div>
              <dt>{strings.licenceLabel}</dt>
              <dd>{strings.licence}</dd>
            </div>
          </dl>
        </section>
      </main>
      <footer className="shell-footer">
        <p>
          {PRODUCT_NAME}. {strings.footer}
        </p>
      </footer>
    </div>
  );
}
