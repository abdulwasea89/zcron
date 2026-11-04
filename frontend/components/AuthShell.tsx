import type { ReactNode } from "react";

type AuthShellProps = {
  children: ReactNode;
  eyebrow?: string;
  title: string;
  description?: string;
  footer?: ReactNode;
  wide?: boolean;
};

export function AuthShell({ children, eyebrow, title, description, footer, wide }: AuthShellProps) {
  return (
    <main className="auth-shell">
      <div className={`auth-frame${wide ? " auth-frame-wide" : ""}`}>
        <section className="auth-brand-panel" aria-label="About Zcron">
          <div className="auth-ribbon auth-ribbon-one" aria-hidden="true" />
          <div className="auth-ribbon auth-ribbon-two" aria-hidden="true" />
          <div className="auth-ribbon auth-ribbon-three" aria-hidden="true" />
          <div className="auth-brand-panel-inner">
            <div className="auth-brand-header">
              <span className="auth-brand-name">Zcron</span>
            </div>

            <blockquote className="auth-brand-quote">
              <p>Keep your venue<br />in motion.</p>
              <footer>Every member, payment, and team moment — in sync.</footer>
            </blockquote>

            <div className="auth-brand-features">
              <div className="auth-brand-feature">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16.7 5.3L7.5 14.5 3.3 10.3" /></svg>
                Built for independent venues
              </div>
              <div className="auth-brand-feature">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16.7 5.3L7.5 14.5 3.3 10.3" /></svg>
                Secure by design
              </div>
            </div>
          </div>
        </section>

        <section className="auth-form-panel">
          <div className="auth-form-panel-inner">
            <div className="auth-mobile-brand">
              <span className="auth-brand-name">Zcron</span>
            </div>

            <header className="auth-heading">
              {eyebrow && <p className="auth-eyebrow">{eyebrow}</p>}
              <h1>{title}</h1>
              {description && <p className="auth-heading-desc">{description}</p>}
            </header>

            {children}

            {footer && <footer className="auth-footer">{footer}</footer>}
          </div>
        </section>
      </div>
    </main>
  );
}
