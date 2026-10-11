"use client";

/* TEMPORARY render harness — delete after eyeballing.

   /app/plans sits behind auth. This renders the *real* PlansPage (no copied
   markup) with the API stubbed, so what gets screenshotted is exactly what
   ships. The stub patches window.fetch at module scope, which runs before
   React renders and therefore before the page's own effects fire. */

import PlansPage from "@/app/app/plans/page";
import { ChatInput } from "@/components/ChatInput";

const PLANS = [
  { id: "1", name: "002", public_description: "Flexible fixed desk in the north wing, all utilities included.", price: 2, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "recurring", visibility: "public", status: "published", featured: true, offer_kind: "space", spec: { space_type: "fixed_desk", term: "monthly", billing: "company_invoice", room_credits: 4 } },
  { id: "2", name: "ss", public_description: null, price: 149, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "recurring", visibility: "members_only", status: "published", featured: false, offer_kind: "space", spec: { space_type: "hot_desk", term: "monthly" } },
  { id: "3", name: "dff", public_description: null, price: 200, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "one_time_pack", visibility: "public", status: "draft", featured: false, offer_kind: "space" },
  { id: "4", name: "jj", public_description: null, price: 25, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "drop_in", visibility: "invite_only", status: "paused", featured: false, offer_kind: "space" },
  { id: "5", name: "d", public_description: null, price: 189, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "recurring", visibility: "public", status: "published", featured: false, offer_kind: "space" },
  { id: "6", name: "Meeting room — 4h block", public_description: null, price: 120, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "one_time_pack", visibility: "members_only", status: "archived", featured: false, offer_kind: "space" },
  { id: "7", name: "Private office (6 seats)", public_description: null, price: 2400, currency: "USD", tax_mode: "exclusive", tax_rate: 0, billing_type: "recurring", visibility: "invite_only", status: "archived", featured: true, offer_kind: "space" },
];

if (typeof window !== "undefined") {
  const real = window.fetch.bind(window);
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
    if (url.includes("/api/proxy/plans")) return json(PLANS);
    if (url.includes("/api/proxy/organizations/me")) {
      return json({ id: "o1", name: "SK Boxing", industry: "office", currency: "USD", timezone: "UTC" });
    }
    if (url.includes("/api/proxy/")) return json({});
    return real(input as RequestInfo, init);
  }) as typeof window.fetch;
}

export default function ScratchPage() {
  return (
    <main className="bg-background">
      <div className="mx-auto w-full px-8 py-10 lg:max-w-[1240px]">
        <PlansPage />
      </div>
    </main>
  );
}
