"use client";

import { useState } from "react";
import { Alert, Button, Card, CardHeader, Input, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { MemberProfile } from "@/lib/types";

type EditableField = Exclude<keyof MemberProfile, "summary">;
type ProfileForm = Record<EditableField, string>;

function formFrom(profile: MemberProfile): ProfileForm {
  return {
    display_name: profile.display_name ?? "",
    phone: profile.phone ?? "",
    photo_url: profile.photo_url ?? "",
    emergency_contact: profile.emergency_contact ?? "",
    goals: profile.goals ?? "",
    health_notes: profile.health_notes ?? "",
    id_document_type: profile.id_document_type ?? "",
    id_document_last4: profile.id_document_last4 ?? "",
  };
}

export function MemberProfileCard({ memberId, profile, canManage, onSaved }: {
  memberId: string;
  profile: MemberProfile;
  canManage: boolean;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<ProfileForm>(() => formFrom(profile));
  const change = (field: EditableField, value: string) => setForm((current) => ({ ...current, [field]: value }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      await api.patch(`/members/${memberId}/profile`, Object.fromEntries(
        Object.entries(form).map(([key, value]) => [key, value.trim() || null]),
      ));
      setEditing(false);
      await onSaved();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save the member profile.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Member profile"
        subtitle="Goals, emergency details and private notes"
        action={canManage && !editing ? <Button variant="secondary" onClick={() => setEditing(true)}>Edit profile</Button> : undefined}
      />
      <div className="space-y-4 p-5">
        {error && <Alert>{error}</Alert>}
        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="Display name" value={form.display_name} maxLength={160} onChange={(event) => change("display_name", event.target.value)} />
              <Input label="Phone" type="tel" value={form.phone} maxLength={40} onChange={(event) => change("phone", event.target.value)} />
              <Input label="Photo URL" type="url" placeholder="https://…" value={form.photo_url} maxLength={2048} onChange={(event) => change("photo_url", event.target.value)} />
              <Input label="Emergency contact" value={form.emergency_contact} maxLength={120} onChange={(event) => change("emergency_contact", event.target.value)} />
            </div>
            <Textarea label="Goals" rows={3} maxLength={1000} value={form.goals} onChange={(event) => change("goals", event.target.value)} />
            <Textarea label="Private health notes" rows={3} maxLength={2000} value={form.health_notes} onChange={(event) => change("health_notes", event.target.value)} />
            <p className="text-xs text-muted-foreground">Record only information the member chooses to share. Health notes are visible to the member, owner and managers.</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-xs text-muted-foreground">ID document type
                <select value={form.id_document_type} onChange={(event) => change("id_document_type", event.target.value)} className="mt-1 block h-9 w-full border border-foreground/20 bg-card px-3 text-sm text-foreground">
                  <option value="">None</option>
                  <option value="national_id">National ID</option>
                  <option value="passport">Passport</option>
                  <option value="driver_license">Driver license</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <Input label="ID final four" value={form.id_document_last4} maxLength={4} onChange={(event) => change("id_document_last4", event.target.value)} />
            </div>
            <p className="text-xs text-muted-foreground">Use ID details only where local rules permit. Never enter a full ID number or document image.</p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" disabled={saving} onClick={() => { setForm(formFrom(profile)); setEditing(false); setError(""); }}>Cancel</Button>
              <Button disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save profile"}</Button>
            </div>
          </div>
        ) : (
          <>
            <div>
              <p className="text-xs font-medium text-muted-foreground">Current summary</p>
              <p className="mt-1 text-sm text-foreground">{profile.summary}</p>
            </div>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div><dt className="text-xs text-muted-foreground">Goals</dt><dd className="mt-1 whitespace-pre-wrap text-sm">{profile.goals || "—"}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Emergency contact</dt><dd className="mt-1 text-sm">{profile.emergency_contact || "—"}</dd></div>
              {canManage && <div><dt className="text-xs text-muted-foreground">ID reference</dt><dd className="mt-1 text-sm">{profile.id_document_last4 ? `${(profile.id_document_type || "ID").replaceAll("_", " ")} ending ${profile.id_document_last4}` : "—"}</dd></div>}
              {canManage && <div><dt className="text-xs text-muted-foreground">Private health notes</dt><dd className="mt-1 whitespace-pre-wrap text-sm">{profile.health_notes || "—"}</dd></div>}
            </dl>
          </>
        )}
      </div>
    </Card>
  );
}
