"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Alert, Button, Input } from "@/components/ui";
import { accountSchema, collectErrors } from "@/lib/validation/register";
import { checkPwned } from "@/lib/hibp";

function cx(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(" ");
}

function Steps({ current, labels }: { current: number; labels: string[] }) {
  return (
    <ol className="mb-8 flex items-center gap-2" aria-label={`Step ${current} of ${labels.length}`}>
      {labels.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const active = n === current;
        const reached = done || active;
        return (
          <li key={label} className="min-w-0 flex-1" aria-current={active ? "step" : undefined}>
            <span
              className={cx(
                "block h-1 rounded-full transition-colors duration-300",
                done ? "bg-[var(--foreground)]" : active ? "bg-[var(--foreground)]" : "bg-[var(--border)]",
              )}
            />
            <span
              className={cx(
                "mt-2 flex items-center gap-1.5 truncate text-[10px] font-semibold leading-tight transition-colors duration-300",
                reached ? "text-[var(--foreground)]" : "text-[var(--muted)]",
              )}
            >
              <span className="tabular-nums opacity-60">{n}</span>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [breached, setBreached] = useState<null | { count: number }>(null);
  const [checkingBreach, setCheckingBreach] = useState(false);
  const breachTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const stepLabels = ["Account", "Verify"];


  const firstInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstInputRef.current?.focus();
  }, [step]);

  async function post(path: string, body: unknown) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong");
    return data;
  }

  const clearField = (key: string) => setFieldErrors((p) => ({ ...p, [key]: "" }));

  const passwordRules = [
    { label: "12+ characters", met: password.length >= 12 },
    { label: "Uppercase", met: /[A-Z]/.test(password) },
    { label: "Lowercase", met: /[a-z]/.test(password) },
    { label: "Number", met: /[0-9]/.test(password) },
    { label: "Symbol", met: /[^A-Za-z0-9]/.test(password) },
  ];

  // 0–4 scale across 4 bars: all 5 rules met → 4 filled green bars.
  const metCount = passwordRules.filter((r) => r.met).length;
  const strength =
    !password ? 0
    : metCount <= 2 ? 1
    : metCount === 3 ? 2
    : metCount === 4 ? 3
    : 4;
  const strengthTone = ["weak", "weak", "fair", "good", "strong"][strength];
  const strengthLabel = ["", "Weak", "Fair", "Good", "Strong"][strength];

  // HIBP breach check via k-anonymity (Section 4.2 / Security Rule #5).
  // Only fires once all 5 complexity rules are met.
  const allRulesMet = metCount === 5;

  async function checkBreach() {
    if (!allRulesMet) { setBreached(null); return; }
    setCheckingBreach(true);
    try {
      const result = await checkPwned(password);
      setBreached(result.pwned ? { count: result.count } : null);
    } finally {
      setCheckingBreach(false);
    }
  }

  useEffect(() => {
    if (breachTimerRef.current) clearTimeout(breachTimerRef.current);
    if (!allRulesMet) { queueMicrotask(() => setBreached(null)); return; }
    breachTimerRef.current = setTimeout(checkBreach, 700);
    return () => { if (breachTimerRef.current) clearTimeout(breachTimerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [password]);

  function validateAccount(): boolean {
    const { success, errors } = collectErrors(accountSchema, { email, password, confirm });
    setFieldErrors(errors);
    return success;
  }

  function goBack() {
    setError("");
    setFieldErrors({});
    setStep((s) => Math.max(1, s - 1));
  }

  async function submitAccount(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!validateAccount()) return;
    if (breached) {
      setError("This password appears in a data breach. Choose a different one.");
      return;
    }
    setFieldErrors({});
    setLoading(true);
    try {
      await post("/api/auth/register", { email, password, confirm_password: confirm });
      setStep(2);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function submitVerify(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setFieldErrors({});
    if (!code.trim()) { setFieldErrors({ code: "Required" }); return; }
    setLoading(true);
    try {
      await post("/api/auth/verify-email", { email, code });
      router.push("/app");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function resendCode() {
    setError(""); setNotice(""); setLoading(true);
    try {
      await post("/api/auth/resend-code", { email });
      setNotice("A new verification code was sent.");
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  }

  const titles = ["Create your account", "Check your inbox"];
  const descriptions = [
    "Start with your email and a strong password. You’ll finish workspace setup after verifying your email.",
    `We sent a 6-digit code to ${email}.`,
  ];

  return (
    <AuthShell
      wide={false}
      eyebrow={`Step ${step} of ${stepLabels.length}`}
      title={titles[step - 1]}
      description={descriptions[step - 1]}
      footer={<>Already have an account? <Link href="/login" className="auth-link">Sign in</Link></>}
    >
      <div className="auth-form-card">
        <Steps current={step} labels={stepLabels} />

        {error && (
          <div className="mb-5">
            <Alert onDismiss={() => setError("")}>{error}</Alert>
          </div>
        )}

        <div key={step} className="auth-step-panel">
        {/* Step 1 — Account */}
        {step === 1 && (
          <form onSubmit={submitAccount} className="space-y-4">
            <Input
              ref={firstInputRef}
              label="Work email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => { setEmail(e.target.value); clearField("email"); }}
              placeholder="owner@yourcompany.com"
              error={fieldErrors.email}
            />

            <Input
              label="Password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => { setPassword(e.target.value); clearField("password"); }}
              placeholder="Create a strong password"
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

            <div>
              <div className="password-strength">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className={`password-strength-bar ${i <= strength ? `is-${strengthTone}` : ""}`}
                  />
                ))}
              </div>
              {password && (
                <p className={`password-strength-label is-${strengthTone}`}>
                  {strengthLabel} password
                </p>
              )}
            </div>

            <div className="password-rules" aria-label="Password requirements">
              {passwordRules.map((rule) => (
                <span key={rule.label} className={`password-rule ${rule.met ? "is-met" : ""}`}>{rule.label}</span>
              ))}
            </div>

            {breached && (
              <p className="mt-2 text-xs leading-relaxed text-[var(--danger)]">
                ⚠ This password appeared in <strong>{breached.count.toLocaleString()}</strong> data breach{breached.count === 1 ? "" : "es"}.
                Choose a different password.
              </p>
            )}
            {checkingBreach && allRulesMet && !breached && (
              <p className="mt-2 text-xs text-[var(--muted)]">Checking against known breaches…</p>
            )}

            <Input
              label="Confirm password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => { setConfirm(e.target.value); clearField("confirm"); }}
              placeholder="Re-enter your password"
              error={fieldErrors.confirm}
            />

            <Button type="submit" loading={loading} className="w-full">Continue</Button>
          </form>
        )}

        {notice && <p role="status" className="mb-4 text-sm text-[var(--success)]">{notice}</p>}

        {/* Step 2 — Verify email */}
        {step === 2 && (
          <form onSubmit={submitVerify} className="space-y-5">
            <div className="rounded-xl bg-[var(--primary-light)] px-4 py-3.5 text-sm leading-relaxed text-[var(--primary)]">
              Enter the 6-digit code sent to <span className="font-semibold">{email}</span>.
            </div>

            <Input
              ref={firstInputRef}
              label="Verification code"
              inputMode="numeric"
              maxLength={6}
              required
              value={code}
              onChange={(e) => { setCode(e.target.value.replace(/\D/g, "")); setFieldErrors({}); }}
              placeholder="000000"
              autoComplete="one-time-code"
              error={fieldErrors.code}
            />

            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" variant="secondary" onClick={goBack}>Back</Button>
              <Button type="submit" loading={loading} className="flex-1">Verify email</Button>
              <Button type="button" variant="ghost" disabled={loading} onClick={resendCode}>Resend code</Button>
            </div>
          </form>
        )}

        </div>
      </div>
    </AuthShell>
  );
}
