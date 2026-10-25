"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { Alert, Button, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

export default function GymInquiryPage() {
  const { orgCode } = useParams<{ orgCode: string }>();
  const [gymName, setGymName] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get<{ organization_name: string }>(`/leads/public/${encodeURIComponent(orgCode)}`)
      .then((data) => { if (active) setGymName(data.organization_name); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof ApiError ? cause.message : "This inquiry form is unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [orgCode]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    if (!String(data.get("email") ?? "").trim() && !String(data.get("phone") ?? "").trim()) {
      setError("Enter an email address or a phone number so the team can reach you.");
      return;
    }
    setSending(true);
    try {
      await api.post(`/leads/public/${encodeURIComponent(orgCode)}`, {
        name: String(data.get("name") ?? "").trim(),
        email: String(data.get("email") ?? "").trim() || null,
        phone: String(data.get("phone") ?? "").trim() || null,
        goal: String(data.get("goal") ?? "").trim() || null,
        website: String(data.get("website") ?? ""),
      });
      setSent(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not send your inquiry. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
    <section className="w-full max-w-lg border border-border bg-card p-6 shadow-sm sm:p-8">
      {loading ? <p role="status" className="text-sm text-muted-foreground">Loading inquiry form…</p> : error && !gymName ? <Alert tone="danger">{error}</Alert> : sent ? <div role="status" className="space-y-3"><p className="text-xs font-semibold uppercase tracking-wider text-brand">Inquiry sent</p><h1 className="text-2xl font-semibold">Thanks for reaching out.</h1><p className="text-sm leading-6 text-muted-foreground">Your message was sent to {gymName}. The team can follow up using the contact details you provided.</p></div> : <>
        <p className="text-xs font-semibold uppercase tracking-wider text-brand">{gymName}</p>
        <h1 className="mt-2 text-2xl font-semibold">Let’s talk about your goals</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Leave your details and the gym team will get back to you.</p>
        {error && <div className="mt-4"><Alert tone="danger">{error}</Alert></div>}
        <form onSubmit={submit} className="mt-6 space-y-4">
          <Input name="name" label="Your name" autoComplete="name" required maxLength={160} />
          <Input name="email" label="Email address (optional)" type="email" autoComplete="email" maxLength={320} />
          <Input name="phone" label="Phone number (optional)" type="tel" autoComplete="tel" maxLength={40} />
          <label className="block text-sm font-medium text-foreground">What are you looking for?<textarea name="goal" rows={3} maxLength={2000} className="mt-1.5 block w-full resize-y border border-foreground/15 bg-background px-3 py-2 text-sm text-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20" /></label>
          <div aria-hidden="true" className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden"><label>Leave this field empty<input name="website" tabIndex={-1} autoComplete="off" /></label></div>
          <p className="text-xs leading-5 text-muted-foreground">Submitting asks the team to contact you about this inquiry. It does not sign you up for marketing messages or a membership.</p>
          <Button type="submit" loading={sending} disabled={!gymName || loading} className="w-full">Send inquiry</Button>
        </form>
      </>}
    </section>
  </main>;
}
