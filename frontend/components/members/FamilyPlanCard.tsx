"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, Button, Card, CardHeader, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { MemberDetailOut, MemberDirectoryItem } from "@/lib/types";

export function FamilyPlanCard({ detail, canManage, onSaved }: {
  detail: MemberDetailOut; canManage: boolean; onSaved: () => Promise<void>;
}) {
  const [candidates, setCandidates] = useState<MemberDirectoryItem[] | null>(null);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState(detail.subscription?.audience === "family" ? "shared_plan" : "independent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const retryKeys = useRef<Record<string, string>>({});
  const ownerId = detail.member.member_id;
  const family = detail.family_members;
  const capacity = detail.subscription?.family_capacity ?? 1;
  const coveredCount = family.filter((member) => member.billing_mode === "shared_plan").length;
  const canShare = detail.subscription?.audience === "family";
  if (detail.member.role !== "member") return null;
  async function openPicker() {
    setError(""); setBusy(true);
    setMode(canShare && coveredCount + 1 < capacity ? "shared_plan" : "independent");
    try {
      setCandidates((await api.get<MemberDirectoryItem[]>("/members")).filter(
        (member) => member.role === "member" && member.member_id !== ownerId && !family.some((row) => row.member_id === member.member_id),
      ));
    } catch (cause) { setError((cause as ApiError).message || "Could not load members."); }
    finally { setBusy(false); }
  }
  async function changeFamily(memberId: string, attach: boolean) {
    setError(""); setBusy(true);
    const operation = `${memberId}:${attach}:${mode}`;
    const key = retryKeys.current[operation] ||= crypto.randomUUID();
    try {
      if (attach) await api.post(`/members/${ownerId}/family`, { member_id: memberId, billing_mode: mode }, { "Idempotency-Key": key });
      else await api.del(`/members/${ownerId}/family/${memberId}`, { "Idempotency-Key": key });
      delete retryKeys.current[operation];
      setCandidates(null); setSelected("");
      toast.success(attach ? "Household member linked." : "Household link removed.");
      try { await onSaved(); } catch { setError("Household saved. Reload member details to see the update."); }
    } catch (cause) { setError((cause as ApiError).message || "Could not update the household."); }
    finally { setBusy(false); }
  }
  return <Card>
    <CardHeader title="Family and household" subtitle={detail.family_owner ? (detail.family_owner.billing_mode === "independent" ? "Linked household · independently billed" : "Covered by a shared family plan") : `${family.length + 1} linked members${canShare ? ` · ${coveredCount + 1}/${capacity} shared-plan places` : ""}`} />
    <div className="space-y-4 p-5">
      {error && <Alert>{error}</Alert>}
      {detail.family_owner ? <p className="text-sm">{detail.family_owner.billing_mode === "independent" ? "Household contact" : "Plan holder"}: <Link className="underline underline-offset-4" href={`/app/members?member=${detail.family_owner.member_id}`}>{detail.family_owner.name}</Link></p> : <>
        {family.length ? <ul className="space-y-2">{family.map((member) => <li key={member.member_id} className="flex items-center justify-between gap-3 border-b border-border pb-2 text-sm">
          <div><Link className="underline underline-offset-4" href={`/app/members?member=${member.member_id}`}>{member.name}</Link><p className="mt-1 text-xs text-muted-foreground">{member.billing_mode === "independent" ? "Own subscription and payments" : "Shared plan and visit credits"}</p></div>
          {canManage && <Button variant="secondary" disabled={busy} onClick={() => void changeFamily(member.member_id, false)}>Remove</Button>}
        </li>)}</ul> : <p className="text-sm text-muted-foreground">No linked household members.</p>}
        {canManage && family.length < 19 && (candidates ? <div className="space-y-3">
          <Select label="Billing arrangement" disabled={busy} value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="independent">Separate subscription for each payer</option>
            {canShare && coveredCount + 1 < capacity && <option value="shared_plan">Covered by this family plan</option>}
          </Select>
          <Select label="Member" value={selected} disabled={busy} onChange={(event) => setSelected(event.target.value)}><option value="">Choose member</option>{candidates.map((member) => <option key={member.member_id} value={member.member_id}>{member.display_name || member.full_name || member.email}</option>)}</Select>
          <div className="flex gap-2"><Button disabled={!selected || busy || (mode === "shared_plan" && coveredCount + 1 >= capacity)} onClick={() => void changeFamily(selected, true)}>Link member</Button><Button variant="secondary" disabled={busy} onClick={() => setCandidates(null)}>Cancel</Button></div>
        </div> : <Button variant="secondary" disabled={busy} onClick={() => void openPicker()}>Add household member</Button>)}
      </>}
      <p className="text-xs leading-5 text-muted-foreground">Independently billed members keep their own prices, renewal dates, payments, and visit credits. Linking a household does not charge anyone or grant access. Shared-plan members use the plan holder’s coverage and credits.</p>
    </div>
  </Card>;
}
