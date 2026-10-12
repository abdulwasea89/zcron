"use client";

import { useState } from "react";
import { Alert, Button, Card, CardHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { MemberDetailOut, MemberDirectoryItem } from "@/lib/types";

export function FamilyPlanCard({ detail, canManage, onSaved }: {
  detail: MemberDetailOut;
  canManage: boolean;
  onSaved: () => Promise<void>;
}) {
  const [candidates, setCandidates] = useState<MemberDirectoryItem[] | null>(null);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ownerId = detail.member.member_id;
  const family = detail.family_members;
  const capacity = detail.subscription?.family_capacity;
  const isOwner = detail.subscription?.audience === "family" && !detail.family_owner;

  if (!isOwner && !detail.family_owner) return null;

  async function openPicker() {
    setError("");
    try {
      setCandidates((await api.get<MemberDirectoryItem[]>("/members")).filter(
        (m) => m.role === "member" && m.member_id !== ownerId && !family.some((f) => f.member_id === m.member_id),
      ));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load members.");
    }
  }

  async function changeFamily(memberId: string, attach: boolean) {
    setError("");
    setBusy(true);
    try {
      if (attach) await api.post(`/members/${ownerId}/family`, { member_id: memberId });
      else await api.del(`/members/${ownerId}/family/${memberId}`);
      setCandidates(null);
      setSelected("");
      await onSaved();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not update the family plan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Family plan" subtitle={detail.family_owner ? "This member is covered by another member's plan" : `${family.length + 1} of ${capacity ?? 1} places used`} />
      <div className="space-y-4 p-5">
        {error && <Alert>{error}</Alert>}
        {detail.family_owner ? <p className="text-sm">Plan holder: {detail.family_owner.name}</p> : (
          <>
            {family.length ? <ul className="space-y-2">{family.map((member) => <li key={member.member_id} className="flex items-center justify-between gap-3 border-b border-foreground/10 pb-2 text-sm">
              <span>{member.name}</span>
              {canManage && <Button variant="secondary" disabled={busy} onClick={() => void changeFamily(member.member_id, false)}>Remove</Button>}
            </li>)}</ul> : <p className="text-sm text-muted-foreground">No additional family members yet.</p>}
            {canManage && capacity && family.length + 1 < capacity && (candidates ? (
              <div className="flex flex-wrap items-end gap-2">
                <label className="min-w-48 flex-1 text-xs text-muted-foreground">Add a member
                  <select className="mt-1 block h-9 w-full border border-foreground/20 bg-card px-3 text-sm text-foreground" value={selected} onChange={(event) => setSelected(event.target.value)}>
                    <option value="">Choose member</option>
                    {candidates.map((member) => <option key={member.member_id} value={member.member_id}>{member.display_name || member.full_name || member.email}</option>)}
                  </select>
                </label>
                <Button disabled={!selected || busy} onClick={() => void changeFamily(selected, true)}>Add to plan</Button>
                <Button variant="secondary" disabled={busy} onClick={() => setCandidates(null)}>Cancel</Button>
              </div>
            ) : <Button variant="secondary" onClick={() => void openPicker()}>Add family member</Button>)}
            <p className="text-xs text-muted-foreground">Covered members share this plan and its remaining visit credits.</p>
          </>
        )}
      </div>
    </Card>
  );
}
