"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Alert, Button, Input } from "@/components/ui";
import { loginSchema } from "@/lib/validation/auth";
import { collectErrors } from "@/lib/validation/shared";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/app";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [orgCode, setOrgCode] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    emailRef.current?.focus();
  }, []);

  function validate(): boolean {
    const { success, errors } = collectErrors(loginSchema, { email, password, orgCode });
    setFieldErrors(errors);
    return success;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!validate()) return;
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          org_code: orgCode || null,
          mfa_code: mfaCode || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid credentials");
      if (data.requires_mfa) {
        setNeedsMfa(true);
        setError("");
        return;
      }
      router.push(next);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title={needsMfa ? "One more quick check" : "Welcome back"}
      description={needsMfa ? "Enter the code from your authenticator app to continue securely." : undefined}
      footer={<>New to Zcron? <Link href="/register" className="auth-link">Create your organization</Link></>}
    >
      <div className="auth-form-card auth-login-form">
        {error && (
          <div className="mb-5">
            <Alert onDismiss={() => setError("")}>{error}</Alert>
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-5">
          {!needsMfa ? (
            <>
              <Input
                ref={emailRef}
                label="Work email"
                labelVariant="sentence"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => { setEmail(e.target.value); setFieldErrors((p) => ({ ...p, email: "" })); }}
                placeholder="you@yourcompany.com"
                error={fieldErrors.email}
              />

              <Input
                label="Password"
                labelVariant="sentence"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFieldErrors((p) => ({ ...p, password: "" })); }}
                placeholder="Enter your password"
                error={fieldErrors.password}
                trailing={
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                }
              />

              <Input
                label="Org code"
                labelVariant="sentence"
                value={orgCode}
                onChange={(e) => { setOrgCode(e.target.value.toUpperCase()); setFieldErrors((p) => ({ ...p, orgCode: "" })); }}
                placeholder="IRON-PULS-3K9"
                hint="Leave blank to go to your last organization"
                autoComplete="organization"
                error={fieldErrors.orgCode}
              />

              <div className="flex items-center justify-between gap-4">
                <Link
                  href="/recover-codes"
                  className="text-sm font-medium text-[var(--muted)]  transition-colors"
                >
                  Don&apos;t remember your org code?
                </Link>
                <Link
                  href="/forgot-password"
                  className="text-sm font-medium  text-[var(--muted)]  hover:underline shrink-0"
                >
                  Forgot password?
                </Link>
              </div>

              <Button type="submit" loading={loading} className="w-full">
                Sign in
              </Button>
            </>
          ) : (
            <>
              <div className="rounded-xl bg-[var(--primary-light)] px-4 py-3.5 text-sm leading-relaxed text-[var(--primary)]">
                Open your authenticator app and enter the 6-digit code for Zcron.
              </div>

              <Input
                label="Authenticator code"
                labelVariant="sentence"
                inputMode="numeric"
                maxLength={6}
                required
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                autoComplete="one-time-code"
              />

              <Button type="submit" loading={loading} className="w-full">
                Verify & sign in
              </Button>
            </>
          )}
        </form>

        {!needsMfa && (
          <div className="auth-divider-wrap">
            <div className="auth-divider">or</div>
            <div className="text-center">
              <Link href="/magic-link" className="text-sm font-medium text-[var(--primary)] hover:underline">
                Send a secure sign-in link instead
              </Link>
            </div>
          </div>
        )}
      </div>
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)]" />
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
