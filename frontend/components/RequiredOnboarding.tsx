"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { z } from "zod";
import { Alert, Button, Input, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { collectErrors, CNIC_RE, NAME_RE, PHONE_RE } from "@/lib/validation/shared";

type Checkout = { checkout_url: string; session_id: string };
type OnboardingDefaults = {
  full_name?: string | null; phone?: string | null; occupation?: string | null;
  education?: string | null; address?: string | null; city?: string | null;
  date_of_birth?: string | null; gender?: string | null; emergency_contact?: string | null;
  venue?: string; industry?: string; country?: string; timezone?: string; currency?: string;
};

const tiers = [
  { id: "starter", title: "Starter", price: 29, detail: "For a small team" },
  { id: "pro", title: "Pro", price: 79, detail: "For a growing operation" },
] as const;

const optionalText = (max: number, label: string) => z.string().trim().max(max, `${label} must be ${max} characters or fewer`);
const validIsoDate = (value: string) => {
  if (!value) return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};
const profileSchema = z.object({
  fullName: z.string().trim().min(2, "Enter your full name").max(100, "Name must be 100 characters or fewer")
    .regex(NAME_RE, "Use letters, spaces, apostrophes, periods, or hyphens"),
  phone: z.string().trim().refine((value) => !value || PHONE_RE.test(value.replace(/[\s\-()]/g, "")), "Enter a valid phone number (7–15 digits)"),
  cnic: z.string().trim().refine((value) => !value || (value.length <= 15 && CNIC_RE.test(value)), "Enter a 13-digit ID, for example 42101-1234567-8"),
  occupation: optionalText(100, "Occupation"),
  education: optionalText(100, "Education"),
  address: optionalText(200, "Address"),
  city: optionalText(85, "City"),
  dateOfBirth: z.string().refine(validIsoDate, "Enter a valid date"),
  gender: z.enum(["", "male", "female", "other"]),
  emergencyContact: optionalText(120, "Emergency contact"),
});
const workspaceSchema = z.object({
  venue: z.string().trim().min(2, "Enter a workspace name").max(80, "Workspace name must be 80 characters or fewer"),
  industry: z.enum(["gym", "office", "academy"]),
  country: z.string().trim().regex(/^[A-Za-z]{2}$/, "Enter a 2-letter country code (for example US)"),
  timezone: z.string().trim().min(1, "Enter a timezone, such as America/New_York"),
  currency: z.string().trim().regex(/^[A-Za-z]{3}$/, "Choose a 3-letter currency code"),
});

export function RequiredOnboarding({ email, initial }: { email: string; initial: OnboardingDefaults }) {
  const dialogRef = useRef<HTMLElement>(null);
  const searchParams = useSearchParams();
  const checkoutSession = searchParams.get("session_id");
  const paymentCancelled = searchParams.get("onboarding") === "payment-cancelled";
  const [fullName, setFullName] = useState(initial.full_name ?? "");
  const [phone, setPhone] = useState(initial.phone ?? "");
  const [cnic, setCnic] = useState("");
  const [occupation, setOccupation] = useState(initial.occupation ?? "");
  const [education, setEducation] = useState(initial.education ?? "");
  const [address, setAddress] = useState(initial.address ?? "");
  const [city, setCity] = useState(initial.city ?? "");
  const [dateOfBirth, setDateOfBirth] = useState(initial.date_of_birth ?? "");
  const [gender, setGender] = useState(initial.gender ?? "");
  const [emergencyContact, setEmergencyContact] = useState(initial.emergency_contact ?? "");
  const [venue, setVenue] = useState(initial.venue ?? "");
  const [industry, setIndustry] = useState(initial.industry ?? "gym");
  const [country, setCountry] = useState(initial.country ?? "US");
  const [timezone, setTimezone] = useState(initial.timezone ?? "UTC");
  const [currency, setCurrency] = useState(initial.currency ?? "USD");
  const [tier, setTier] = useState<(typeof tiers)[number]["id"]>("pro");
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    const root = dialogRef.current;
    if (!root) return;
    root.querySelector<HTMLElement>("input, button, [role=combobox]")?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const containFocus = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); return; }
      if (event.key !== "Tab") return;
      const focusable = Array.from(root.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), select:not(:disabled), [role=combobox]:not([aria-disabled=true])",
      )).filter((el) => el.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", containFocus);
    return () => {
      document.removeEventListener("keydown", containFocus);
      document.body.style.overflow = previousOverflow;
    };
    // The modal stays mounted as the user advances through stages, so this
    // focus and scroll guard only needs to be installed once.
  }, []);
  useEffect(() => {
    if (!checkoutSession) return;
    let stopped = false;
    api.post("/organizations/onboarding/confirm", { session_id: checkoutSession })
      .then(() => {
        if (!stopped) window.location.replace("/app");
      })
      .catch((err) => {
        if (!stopped) {
          setError(err instanceof ApiError ? err.message : "Stripe has not confirmed the payment yet.");
          setNotice("If you just paid, wait a moment and verify again. Your workspace stays locked until Stripe confirms it.");
        }
      })
      .finally(() => { if (!stopped) setBusy(false); });
    return () => { stopped = true; };
  }, [checkoutSession]);

  async function beginCheckout() {
    const profileResult = collectErrors(profileSchema, {
      fullName, phone, cnic, occupation, education, address, city, dateOfBirth, gender, emergencyContact,
    });
    const workspaceResult = collectErrors(workspaceSchema, { venue, industry, country, timezone, currency });
    const errors = { ...profileResult.errors, ...workspaceResult.errors };
    setFieldErrors(errors);
    if (!profileResult.success || !workspaceResult.success) {
      setError("Review the highlighted fields before opening checkout.");
      setBusy(false);
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.post<Checkout>("/organizations/onboarding/checkout", {
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        cnic: cnic.trim() || null,
        occupation: occupation.trim() || null,
        education: education.trim() || null,
        address: address.trim() || null,
        city: city.trim() || null,
        date_of_birth: dateOfBirth || null,
        gender: gender || null,
        emergency_contact: emergencyContact.trim() || null,
        tier,
        details: {
          name: venue.trim(),
          industry,
          country: country.trim().toUpperCase(),
          timezone: timezone.trim(),
          default_currency: currency.trim().toUpperCase(),
        },
      });
      window.location.assign(result.checkout_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open secure checkout.");
      setBusy(false);
    }
  }

  async function retryConfirmation() {
    if (!checkoutSession) return;
    setBusy(true); setError("");
    try {
      await api.post("/organizations/onboarding/confirm", { session_id: checkoutSession });
      window.location.replace("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Stripe has not confirmed the payment yet.");
    } finally { setBusy(false); }
  }

  function validateStep(index: number) {
    const result = index === 0
      ? collectErrors(profileSchema, { fullName, phone, cnic, occupation, education, address, city, dateOfBirth, gender, emergencyContact })
      : collectErrors(workspaceSchema, { venue, industry, country, timezone, currency });
    setFieldErrors((current) => ({ ...current, ...result.errors }));
    if (!result.success) {
      setError("Review the highlighted fields before continuing.");
      const firstInvalid = Object.keys(result.errors)[0];
      requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>(`#${firstInvalid}`)?.focus());
      return false;
    }
    setError("");
    return true;
  }

  function nextStep() {
    if (!validateStep(step)) return;
    setError("");
    setStep((current) => Math.min(current + 1, 2));
  }

  function previousStep() {
    setError("");
    setStep((current) => Math.max(current - 1, 0));
  }

  function handleFormKeyDown(event: React.KeyboardEvent<HTMLFormElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    const target = event.target;
    if (target instanceof HTMLElement && (target.getAttribute("role") === "combobox" || target instanceof HTMLButtonElement)) return;
    event.preventDefault();
    if (step < 2) nextStep();
  }

  function fieldError(name: string) { return fieldErrors[name]; }
  function updateField(name: string, update: () => void) {
    update();
    setFieldErrors((current) => {
      if (!(name in current)) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  }

  const stages = ["Your profile", "Workspace", "Plan & payment"];
  const inputClass = "w-full";
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center overflow-y-auto p-3 sm:p-6">
      <div className="absolute inset-0 bg-black/15 backdrop-blur-[2px]" aria-hidden="true" />
      <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="owner-onboarding-title" tabIndex={-1}
        className="relative z-10 flex h-[88vh] w-full max-w-3xl animate-dialog-in flex-col overflow-hidden rounded-lg border border-border bg-popover shadow-2xl">
        <header className="shrink-0 border-b border-border px-5 py-4 sm:px-7">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-brand">Workspace setup</p>
              <h1 id="owner-onboarding-title" className="mt-1 text-lg font-semibold">{checkoutSession ? "Confirming your payment" : stages[step]}</h1>
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">{checkoutSession ? "Stripe" : `Step ${step + 1} of ${stages.length}`}</span>
          </div>
          {!checkoutSession && (
            <ol className="mt-4 grid grid-cols-3 gap-2" aria-label="Workspace setup progress">
              {stages.map((label, index) => (
                <li key={label} aria-current={step === index ? "step" : undefined}>
                  <div className={`h-1 rounded-full transition-colors duration-300 ${index <= step ? "bg-brand" : "bg-foreground/10"}`} />
                  <span className={`mt-1.5 block truncate text-[10px] ${index === step ? "font-medium text-foreground" : "text-muted-foreground"}`}>{label}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-2 text-xs text-muted-foreground">Verified email: <span className="text-foreground">{email}</span></p>
        </header>

        <form onSubmit={(event) => event.preventDefault()} onKeyDown={handleFormKeyDown} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
            <div key={checkoutSession ? "checkout" : step} className="animate-dialog-in space-y-5">
              {error ? <Alert>{error}</Alert> : null}
              {paymentCancelled ? <p role="status" className="text-sm text-muted-foreground">Checkout was cancelled. Your workspace is saved. Choose a plan when you’re ready to try again.</p> : null}
              {notice ? <p role="status" className="text-sm text-muted-foreground">{notice}</p> : null}

              {checkoutSession ? (
                <div className="grid min-h-56 place-content-center justify-items-center gap-4 text-center">
                  <span className="h-8 w-8 animate-spin rounded-full border-2 border-brand/25 border-t-brand" aria-hidden="true" />
                  <div><p className="text-sm font-medium">Checking your payment with Stripe</p><p className="mt-1 text-xs text-muted-foreground">Your workspace stays locked until Stripe confirms the subscription.</p></div>
                  <Button type="button" variant="secondary" loading={busy} onClick={retryConfirmation}>Check again</Button>
                </div>
              ) : step === 0 ? (
                <div>
                  <p className="mb-4 text-sm text-muted-foreground">Add the owner details your team will use in workspace records.</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input id="fullName" className={inputClass} label="Full name" required value={fullName} error={fieldError("fullName")} onChange={(e) => updateField("fullName", () => setFullName(e.target.value))} autoComplete="name" />
                    <Input id="phone" className={inputClass} label="Phone" type="tel" value={phone} error={fieldError("phone")} onChange={(e) => updateField("phone", () => setPhone(e.target.value))} autoComplete="tel" />
                    <Input id="cnic" className={inputClass} label="CNIC / National ID (optional)" value={cnic} error={fieldError("cnic")} onChange={(e) => updateField("cnic", () => setCnic(e.target.value))} />
                    <Input id="occupation" className={inputClass} label="Occupation" value={occupation} error={fieldError("occupation")} onChange={(e) => updateField("occupation", () => setOccupation(e.target.value))} />
                    <Input id="education" className={inputClass} label="Education" value={education} error={fieldError("education")} onChange={(e) => updateField("education", () => setEducation(e.target.value))} />
                    <Input id="dateOfBirth" className={inputClass} label="Date of birth" type="date" value={dateOfBirth} error={fieldError("dateOfBirth")} onChange={(e) => updateField("dateOfBirth", () => setDateOfBirth(e.target.value))} />
                    <Select id="gender" label="Gender" value={gender} error={fieldError("gender")} onChange={(e) => updateField("gender", () => setGender(e.target.value))}>
                      <option value="">Prefer not to say</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
                    </Select>
                    <Input id="emergencyContact" className={inputClass} label="Emergency contact" value={emergencyContact} error={fieldError("emergencyContact")} onChange={(e) => updateField("emergencyContact", () => setEmergencyContact(e.target.value))} />
                    <Input id="address" className="sm:col-span-2" label="Address" value={address} error={fieldError("address")} onChange={(e) => updateField("address", () => setAddress(e.target.value))} autoComplete="street-address" />
                    <Input id="city" label="City" value={city} error={fieldError("city")} onChange={(e) => updateField("city", () => setCity(e.target.value))} autoComplete="address-level2" />
                  </div>
                </div>
              ) : step === 1 ? (
                <div>
                  <p className="mb-4 text-sm text-muted-foreground">Set the workspace identity and regional defaults. You can adjust these later in settings.</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input id="venue" className="sm:col-span-2" label="Workspace name" required value={venue} error={fieldError("venue")} onChange={(e) => updateField("venue", () => setVenue(e.target.value))} autoComplete="organization" />
                    <Select id="industry" label="Business type" value={industry} error={fieldError("industry")} onChange={(e) => updateField("industry", () => setIndustry(e.target.value))}>
                      <option value="gym">Gym / fitness</option><option value="office">Office space</option><option value="academy">Academy</option>
                    </Select>
                    <Input id="country" label="Country code" required maxLength={2} value={country} error={fieldError("country")} onChange={(e) => updateField("country", () => setCountry(e.target.value.toUpperCase()))} />
                    <Input id="timezone" label="Timezone" required value={timezone} error={fieldError("timezone")} onChange={(e) => updateField("timezone", () => setTimezone(e.target.value))} />
                    <Select id="currency" label="Workspace currency" value={currency} error={fieldError("currency")} onChange={(e) => updateField("currency", () => setCurrency(e.target.value))}>
                      <option value="USD">USD — US Dollar</option><option value="EUR">EUR — Euro</option><option value="GBP">GBP — British Pound</option><option value="PKR">PKR — Pakistani Rupee</option>
                    </Select>
                  </div>
                </div>
              ) : (
                <div>
                  <p className="mb-4 text-sm text-muted-foreground">Choose the monthly workspace plan. Billing is in USD and handled securely by Stripe.</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {tiers.map((item) => <button key={item.id} type="button" onClick={() => setTier(item.id)} aria-pressed={tier === item.id}
                      className={`rounded-md border p-4 text-left transition ${tier === item.id ? "border-brand bg-brand/10 ring-1 ring-brand/40" : "border-border hover:border-foreground/30"}`}>
                      <span className="flex items-center justify-between gap-2"><strong>{item.title}</strong><strong>${item.price}<small className="font-normal text-muted-foreground"> / month</small></strong></span>
                      <span className="mt-1 block text-xs text-muted-foreground">{item.detail}</span>
                    </button>)}
                  </div>
                  <div className="mt-5 border-t border-border pt-4">
                    <p className="text-xs leading-5 text-muted-foreground">Stripe collects and stores card details. Acron never receives your full card number. You’ll review the recurring amount on Stripe’s secure checkout page.</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {!checkoutSession && (
            <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-4 sm:px-7">
              {step > 0 ? <Button type="button" variant="secondary" onClick={previousStep}>Back</Button> : <span className="text-xs text-muted-foreground">Your progress is saved as you continue</span>}
              {step < 2 ? (
                <Button type="button" onClick={nextStep}>Next</Button>
              ) : (
                <Button type="button" loading={busy} disabled={busy || !venue.trim() || !fullName.trim()} onClick={() => void beginCheckout()}>Continue to secure Stripe checkout</Button>
              )}
            </footer>
          )}
        </form>
      </section>
    </div>
  );
}
