"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { PlanOut } from "@/lib/types";

type Promotion = {
  id: string; code: string; plan_id: string | null; discount_type: "percent" | "fixed";
  discount_value: number; active: boolean; starts_at: string | null; ends_at: string | null;
};

export function PromotionsPanel({ plans }: { plans: PlanOut[] }) {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [code, setCode] = useState("");
  const [planId, setPlanId] = useState("");
  const [type, setType] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setPromotions(await api.get<Promotion[]>("/promotions")); }
    catch (e) { setError((e as ApiError).message); }
  }
  useEffect(() => { void load(); }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError(""); setBusy(true);
    try {
      await api.post("/promotions", {
        code: code.trim().toUpperCase(), plan_id: planId || null,
        discount_type: type, discount_value: Number(value),
      });
      setCode(""); setValue(""); await load();
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function toggle(promo: Promotion) {
    setError("");
    try { await api.patch(`/promotions/${promo.id}`, { active: !promo.active }); await load(); }
    catch (e) { setError((e as ApiError).message); }
  }

  return <section className="mt-8 border border-[var(--border)] bg-[var(--card)] p-5">
    <h2 className="text-base font-semibold">Promo codes</h2>
    <p className="mt-1 text-sm text-muted-foreground">Discounts apply to the plan price before tax. Joining fees stay separate.</p>
    {error && <div className="mt-4"><Alert onDismiss={() => setError("")}>{error}</Alert></div>}
    <form onSubmit={create} className="mt-5 grid gap-3 sm:grid-cols-[1fr_1fr_1fr_1fr_auto] sm:items-end">
      <Input label="Code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="WELCOME10" required minLength={3} maxLength={32} />
      <label className="text-sm">Plan
        <select className="mt-1 block h-9 w-full border border-[var(--border)] bg-[var(--background)] px-2" value={planId} onChange={(e) => setPlanId(e.target.value)}>
          <option value="">All plans</option>{plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label className="text-sm">Discount type
        <select className="mt-1 block h-9 w-full border border-[var(--border)] bg-[var(--background)] px-2" value={type} onChange={(e) => setType(e.target.value as "percent" | "fixed")}>
          <option value="percent">Percent</option><option value="fixed">Fixed amount</option>
        </select>
      </label>
      <Input label={type === "percent" ? "Percent off" : "Amount off"} type="number" min="0.01" max={type === "percent" ? "100" : undefined} step="0.01" value={value} onChange={(e) => setValue(e.target.value)} required />
      <Button type="submit" loading={busy}>Create code</Button>
    </form>
    {promotions.length > 0 && <div className="mt-5 divide-y divide-[var(--border)] border-t border-[var(--border)]">
      {promotions.map((promo) => <div key={promo.id} className="flex items-center justify-between gap-4 py-3 text-sm">
        <div><strong>{promo.code}</strong><span className="ml-3 text-muted-foreground">{promo.discount_value}{promo.discount_type === "percent" ? "%" : " fixed"} · {plans.find((p) => p.id === promo.plan_id)?.name ?? "All plans"}</span></div>
        <button type="button" className="text-[var(--primary)] hover:underline" onClick={() => void toggle(promo)}>{promo.active ? "Deactivate" : "Activate"}</button>
      </div>)}
    </div>}
  </section>;
}
