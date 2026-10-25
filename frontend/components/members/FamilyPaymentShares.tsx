"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { CashMemberItem } from "@/lib/types";

export type FamilyShare = { member_id: string; amount: string };

export function FamilyPaymentShares({ memberId, total, value, onChange }: {
  memberId: string; total: number; value: FamilyShare[]; onChange: (shares: FamilyShare[]) => void;
}) {
  const [payers, setPayers] = useState<CashMemberItem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.get<CashMemberItem[]>(`/cash/members/${memberId}/family-payers`)
      .then((rows) => { if (active) setPayers(rows); })
      .catch((cause) => { if (active) setError((cause as ApiError).message || "Could not load family payers."); });
    return () => { active = false; };
  }, [memberId]);
  if (error) return <Alert>{error}</Alert>;
  if (payers.length < 2) return null;
  function startSplit() {
    const minor = Math.round(total * 100);
    const first = Math.floor(minor / 2);
    onChange([{ member_id: payers[0].member_id, amount: (first / 100).toFixed(2) },
      { member_id: payers[1].member_id, amount: ((minor - first) / 100).toFixed(2) }]);
  }
  return <section className="space-y-3 border border-border p-3" aria-label="Family bill payers">
    <h3 className="text-sm font-medium">Family bill payers</h3>
    <p className="text-xs text-muted-foreground">Record who paid each share using the selected payment method. The full bill is recorded once and activates one family subscription.</p>
    {!value.length ? <Button type="button" variant="secondary" disabled={total < 0.02} onClick={startSplit}>Split among family payers</Button> : <>
      {value.map((share, index) => <div key={index} className="grid grid-cols-2 gap-3">
        <label className="text-xs text-muted-foreground">Payer
          <select required aria-label={`Family payer ${index + 1}`} value={share.member_id} onChange={(event) => onChange(value.map((row, i) => i === index ? { ...row, member_id: event.target.value } : row))} className="mt-1.5 h-10 w-full border border-input bg-background px-2 text-sm text-foreground">
            {payers.map((payer) => <option key={payer.member_id} value={payer.member_id}>{payer.full_name || payer.email}</option>)}
          </select>
        </label>
        <Input label="Amount paid" type="number" min="0.01" step="0.01" required value={share.amount} onChange={(event) => onChange(value.map((row, i) => i === index ? { ...row, amount: event.target.value } : row))} />
      </div>)}
      <div className="flex flex-wrap gap-2">
        {value.length < payers.length && <Button type="button" variant="secondary" onClick={() => {
          const next = payers.find((payer) => !value.some((share) => share.member_id === payer.member_id));
          if (next) onChange([...value, { member_id: next.member_id, amount: "" }]);
        }}>Add payer</Button>}
        {value.length > 2 && <Button type="button" variant="secondary" onClick={() => onChange(value.slice(0, -1))}>Remove last payer</Button>}
        <Button type="button" variant="secondary" onClick={() => onChange([])}>Use one payer</Button>
      </div>
    </>}
  </section>;
}
