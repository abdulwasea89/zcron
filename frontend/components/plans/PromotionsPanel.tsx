"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import type { PlanOut } from "@/lib/types";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Glyph } from "@/components/Glyph";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Promotion = {
  id: string;
  code: string;
  plan_id: string | null;
  discount_type: "percent" | "fixed";
  discount_value: number;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
};

export function PromotionsPanel({ plans }: { plans: PlanOut[] }) {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [code, setCode] = useState("");
  const [planId, setPlanId] = useState("");
  const [type, setType] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Promotion | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [composer, setComposer] = useState(false);

  async function load() {
    try {
      setPromotions(await api.get<Promotion[]>("/promotions"));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const parsed = z.object({ code: z.string().trim().min(3).max(32).regex(/^[A-Z0-9_-]+$/), value: z.coerce.number().positive().max(type === "percent" ? 100 : Number.MAX_SAFE_INTEGER) }).safeParse({ code, value });
    if (!parsed.success) { toast.error(parsed.error.issues[0]?.message ?? "Check the promo details."); return; }
    setBusy(true);
    try {
      await api.post("/promotions", {
        code: code.trim().toUpperCase(),
        plan_id: planId || null,
        discount_type: type,
        discount_value: Number(value),
      });
      setCode("");
      setValue("");
      await load();
      setComposer(false);
      toast.success("Promo code created.");
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(promo: Promotion) {
      setError("");
    try {
      await api.patch(`/promotions/${promo.id}`, { active: !promo.active });
      await load();
      toast.success(`Promo code ${promo.active ? "deactivated" : "activated"}.`);
    } catch (e) {
      toast.error((e as ApiError).message);
    }
  }

  async function remove(promoId: string) {
    setError("");
    setDeleteBusy(true);
    try {
      await api.del(`/promotions/${promoId}`);
      setDeleteTarget(null);
      await load();
      toast.success("Promo code deleted.");
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">Promo codes</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Discounts apply to the plan price before tax. Joining fees stay separate.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3"><span className="text-xs text-muted-foreground">{promotions.length} {promotions.length === 1 ? "code" : "codes"}</span><Button onClick={() => setComposer(true)}>Create promo code</Button></div>
      </div>

      <div>
        {error && <div className="mb-4"><Alert onDismiss={() => setError("")}>{error}</Alert></div>}

        <Sheet open={composer} onOpenChange={setComposer}><SheetContent><SheetHeader><SheetTitle>Create promo code</SheetTitle><SheetDescription>Discounts apply to the plan price before tax. Joining fees stay separate.</SheetDescription></SheetHeader><SheetBody>
        <form onSubmit={create} className="flex flex-col gap-4">
          <Input
            label="Code"
            labelVariant="sentence"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="WELCOME10"
            required
            minLength={3}
            maxLength={32}
          />

          <label className="block text-[13px] font-medium text-foreground">
            Applies to
            <Select value={planId || "__all__"} onValueChange={(selected) => setPlanId(selected === "__all__" ? "" : selected)}>
              <SelectTrigger className="mt-1.5 h-9 rounded-none border-[var(--border-strong)] bg-[var(--background)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All plans</SelectItem>
                {plans.map((plan) => <SelectItem key={plan.id} value={plan.id}>{plan.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </label>

          <label className="block text-[13px] font-medium text-foreground">
            Discount type
            <Select value={type} onValueChange={(selected) => setType(selected as "percent" | "fixed")}>
              <SelectTrigger className="mt-1.5 h-9 rounded-none border-[var(--border-strong)] bg-[var(--background)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="percent">Percentage</SelectItem>
                <SelectItem value="fixed">Fixed amount</SelectItem>
              </SelectContent>
            </Select>
          </label>

          <Input
            label={type === "percent" ? "Percent off" : "Amount off"}
            labelVariant="sentence"
            type="number"
            min="0.01"
            max={type === "percent" ? "100" : undefined}
            step="0.01"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={type === "percent" ? "10" : "25.00"}
            required
          />

          <Button type="submit" loading={busy} className="w-full">
            Create code
          </Button>
        </form>
        </SheetBody></SheetContent></Sheet>

        <div className="mt-1">
          {promotions.length === 0 ? (
            <div className="py-5 text-sm text-muted-foreground">
              No promo codes yet. Create one to offer a discount at signup.
            </div>
          ) : (
            <div className="divide-y divide-[var(--border)]">
              <div className="hidden grid-cols-[minmax(140px,1.2fr)_minmax(120px,0.9fr)_minmax(120px,1fr)_minmax(180px,1fr)_32px] gap-3 py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:grid">
                <span>Code</span>
                <span>Discount</span>
                <span>Applies to</span>
                <span className="text-right">Status</span>
                <span />
              </div>
              {promotions.map((promo) => {
                const plan = plans.find((item) => item.id === promo.plan_id);
                const discount = promo.discount_type === "percent"
                  ? `${promo.discount_value}% off`
                  : `${money(promo.discount_value, plan?.currency ?? plans[0]?.currency ?? "USD")} off`;

                return (
                  <div key={promo.id} className="grid grid-cols-1 items-center gap-3 py-3 sm:grid-cols-[minmax(140px,1.2fr)_minmax(120px,0.9fr)_minmax(120px,1fr)_minmax(180px,1fr)_32px]">
                    <span className="w-fit border border-[var(--border-strong)] bg-[var(--background)] px-2.5 py-1 font-mono text-xs font-semibold tracking-wide text-foreground">
                      {promo.code}
                    </span>
                    <span className="text-sm font-medium text-foreground">{discount}</span>
                    <span className="text-sm text-muted-foreground">{plan?.name ?? "All plans"}</span>
                    <div className="flex items-center justify-between gap-3 sm:justify-end">
                      <span className={`px-2 py-1 text-xs ${promo.active ? "text-emerald-400" : "text-muted-foreground"}`}>
                        {promo.active ? "Active" : "Inactive"}
                      </span>
                      <button
                        type="button"
                        aria-label={`${promo.active ? "Deactivate" : "Activate"} ${promo.code}`}
                        className="py-1 text-sm font-medium text-[var(--primary)] transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
                        onClick={() => void toggle(promo)}
                      >
                        {promo.active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                    <button
                      type="button"
                      aria-label={`Delete ${promo.code}`}
                      title="Delete promo code"
                      className="flex h-8 w-8 items-center justify-center text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
                      onClick={() => setDeleteTarget(promo)}
                    >
                      <Glyph className="h-4 w-4"><path d="M3 6h18M8 6V4h8v2m-11 0 1 14h12l1-14M10 11v5m4-5v5" /></Glyph>
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Delete promo code?</AlertDialogTitle>
          <AlertDialogDescription className="mt-3">
            <span className="font-semibold text-foreground">{deleteTarget?.code}</span> will no longer be available to members. This cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel asChild><Button variant="secondary">Cancel</Button></AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" loading={deleteBusy} onClick={() => deleteTarget && void remove(deleteTarget.id)}>Delete code</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
