"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, CardHeader, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export function MemberTagsCard({ memberId, tags, canManage, onSaved }: {
  memberId: string; tags: string[]; canManage: boolean; onSaved: () => Promise<void>;
}) {
  const [value, setValue] = useState(tags.join(", "));
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      await api.put(`/members/${memberId}/tags`, { tags: value.split(",").map((tag) => tag.trim()).filter(Boolean) });
      toast.success("Member tags saved.");
      await onSaved();
    } catch (error) { toast.error((error as ApiError).message || "Could not save tags."); }
    finally { setBusy(false); }
  }
  return <Card><CardHeader title="Member tags" subtitle="Reusable labels for filtering the directory" />
    <div className="space-y-3 p-5">
      <div className="flex flex-wrap gap-2">{tags.length ? tags.map((tag) => <Badge key={tag} tone="neutral">{tag}</Badge>) : <p className="text-sm text-muted-foreground">No tags added.</p>}</div>
      {canManage && <form onSubmit={save} className="space-y-3">
        <Input label="Tags, separated by commas" value={value} onChange={(event) => setValue(event.target.value)} maxLength={658} placeholder="morning, family, strength" />
        <p className="text-xs text-muted-foreground">Up to 20 tags, 32 characters each. Tags ignore capitalization.</p>
        <Button type="submit" variant="secondary" disabled={busy}>Save tags</Button>
      </form>}
    </div></Card>;
}
