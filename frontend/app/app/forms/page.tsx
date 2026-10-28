"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";

type GymForm = {
  id: string; form_key: string; title: string; form_type: "waiver" | "health";
  version: number; body: string; active: boolean; created_at: string;
};
type FormOption = Pick<GymForm, "id" | "title" | "form_type" | "version">;
type Member = { member_id: string; member_name: string | null; member_email: string };
type Acceptance = {
  id: string; member_id: string; form_title: string; form_type: string; form_version: number;
  signed_by_name: string; recorded_at: string; collected_by: string; evidence_filename: string;
};

const errorMessage = (e: unknown) => e instanceof ApiError ? e.message : "Could not load forms.";

export default function FormsPage() {
  const user = useCurrentUser();
  const role = user?.role ?? "";
  const canManage = role === "owner" || role === "manager";
  const canCollect = ["owner", "manager", "front_desk", "trainer"].includes(role);
  const [forms, setForms] = useState<GymForm[]>([]);
  const [options, setOptions] = useState<FormOption[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [memberId, setMemberId] = useState("");
  const [acceptances, setAcceptances] = useState<Acceptance[]>([]);
  const [title, setTitle] = useState("");
  const [formType, setFormType] = useState<"waiver" | "health">("waiver");
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState<GymForm | null>(null);
  const [formId, setFormId] = useState("");
  const [signer, setSigner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [activeForms, visibleOptions] = await Promise.all([
        canManage ? api.get<GymForm[]>("/gym-forms/forms") : Promise.resolve([]),
        api.get<FormOption[]>("/gym-forms/collection-forms"),
      ]);
      setForms(activeForms);
      setOptions(visibleOptions);
      setFormId((current) => visibleOptions.some((form) => form.id === current) ? current : visibleOptions[0]?.id ?? "");
      const roster = role === "trainer"
        ? await api.get<Member[]>("/members/assigned-to-me")
        : await api.get<Member[]>("/attendance/roster");
      setMembers(roster);
      setError("");
    } catch (e) { setError(errorMessage(e)); }
  }, [canManage, role]);

  useEffect(() => {
    if (!role) return;
    async function loadInitialData() { await load(); }
    void loadInitialData();
  }, [load, role]);
  useEffect(() => {
    if (!canManage || !memberId) return;
    api.get<Acceptance[]>(`/gym-forms/members/${memberId}/acceptances`)
      .then(setAcceptances).catch((e) => setError(errorMessage(e)));
  }, [canManage, memberId]);

  const activeForms = forms.filter((form) => form.active);

  function beginEdit(form: GymForm) {
    setEditing(form); setTitle(form.title); setFormType(form.form_type); setBody(form.body);
  }

  async function saveForm() {
    setBusy(true); setError("");
    try {
      const saved = editing
        ? await api.post<GymForm>(`/gym-forms/forms/${editing.id}/versions`, { title, form_type: formType, body })
        : await api.post<GymForm>("/gym-forms/forms", { title, form_type: formType, body });
      setForms((old) => [saved, ...old.map((form) => form.id === editing?.id ? { ...form, active: false } : form)]);
      setOptions((old) => [saved, ...old.filter((form) => form.id !== editing?.id)]);
      setFormId(saved.id); setEditing(null); setTitle(""); setBody("");
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  async function archive(form: GymForm) {
    setBusy(true); setError("");
    try {
      const updated = await api.post<GymForm>(`/gym-forms/forms/${form.id}/archive`);
      setForms((old) => old.map((item) => item.id === updated.id ? updated : item));
      setOptions((old) => old.filter((item) => item.id !== updated.id));
      if (formId === updated.id) setFormId("");
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  async function recordAcceptance(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !memberId || !formId) { setError("Choose a member, active form, and signed file."); return; }
    const data = new FormData(); data.set("form_id", formId); data.set("signed_by_name", signer); data.set("file", file);
    setBusy(true); setError("");
    try {
      await api.post(`/gym-forms/members/${memberId}/acceptances`, data);
      setSigner(""); setFile(null); setFileInputKey((key) => key + 1);
      if (canManage) setAcceptances(await api.get<Acceptance[]>(`/gym-forms/members/${memberId}/acceptances`));
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  if (!user) return <Spinner label="Loading forms..." />;
  if (!canCollect) return <main className="mx-auto max-w-5xl p-6"><Alert>You do not have access to member forms.</Alert></main>;

  return (
    <main className="mx-auto max-w-6xl p-6 sm:p-8">
      <PageHeader title="Waivers & forms" subtitle="Manage gym-authored forms and record signed copies collected by staff." />
      {error && <div className="mb-5"><Alert>{error}</Alert></div>}
      <div className="grid gap-5 xl:grid-cols-2">
        {canManage && <Card>
          <CardHeader title="Form library" subtitle="Edits publish a new version; existing signed copies keep the version originally signed." />
          <div className="space-y-4 p-5">
            <div className="space-y-2">
              {activeForms.map((form) => <div key={form.id} className="flex items-center justify-between gap-3 border-b border-foreground/10 py-2 last:border-0">
                <button type="button" onClick={() => beginEdit(form)} className="min-w-0 text-left hover:text-brand">
                  <span className="block truncate text-sm font-medium">{form.title}</span>
                  <span className="text-xs text-muted-foreground">{form.form_type === "health" ? "Health form" : "Waiver"} · v{form.version}</span>
                </button>
                <Button variant="ghost" disabled={busy} onClick={() => void archive(form)}>Archive</Button>
              </div>)}
              {activeForms.length === 0 && <p className="text-sm text-muted-foreground">No active forms yet.</p>}
            </div>
            <div className="space-y-3 border-t border-foreground/10 pt-4">
              <p className="text-sm font-semibold">{editing ? `Publish a new version of ${editing.title}` : "Create a form"}</p>
              <Input label="Form title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} />
              <label className="block text-xs text-muted-foreground">Type<select className="mt-1 h-9 w-full rounded-md border border-foreground/15 bg-card px-2 text-sm text-foreground" value={formType} onChange={(e) => setFormType(e.target.value as "waiver" | "health")}><option value="waiver">Waiver</option><option value="health">Health form</option></select></label>
              <label className="block text-xs text-muted-foreground">Form text<textarea className="mt-1 min-h-32 w-full rounded-md border border-foreground/15 bg-card p-2 text-sm text-foreground" value={body} onChange={(e) => setBody(e.target.value)} minLength={20} maxLength={20000} /></label>
              <p className="text-xs text-muted-foreground">Use gym-approved wording. Acron does not provide legal or medical templates.</p>
              <div className="flex gap-2"><Button loading={busy} disabled={title.trim().length < 2 || body.trim().length < 20} onClick={() => void saveForm()}>{editing ? "Publish new version" : "Create form"}</Button>{editing && <Button variant="secondary" onClick={() => { setEditing(null); setTitle(""); setBody(""); }}>Cancel</Button>}</div>
            </div>
          </div>
        </Card>}

        <Card>
          <CardHeader title="Record a signed copy" subtitle="Upload a scan or photo collected by staff. Signed evidence is restricted to owners and managers." />
          <form className="space-y-4 p-5" onSubmit={(e) => void recordAcceptance(e)}>
            <label className="block text-xs text-muted-foreground">Member<select required className="mt-1 h-9 w-full rounded-md border border-foreground/15 bg-card px-2 text-sm text-foreground" value={memberId} onChange={(e) => { setAcceptances([]); setMemberId(e.target.value); }}><option value="">Choose a member</option>{members.map((member) => <option key={member.member_id} value={member.member_id}>{member.member_name ?? member.member_email} · {member.member_email}</option>)}</select></label>
            <label className="block text-xs text-muted-foreground">Active form<select required className="mt-1 h-9 w-full rounded-md border border-foreground/15 bg-card px-2 text-sm text-foreground" value={formId} onChange={(e) => setFormId(e.target.value)}><option value="">Choose a form</option>{options.map((form) => <option key={form.id} value={form.id}>{form.title} · v{form.version}</option>)}</select></label>
            <Input label="Name on signed document" value={signer} onChange={(e) => setSigner(e.target.value)} minLength={2} maxLength={160} required />
            <label className="block text-xs text-muted-foreground">Signed document (PDF, PNG, JPEG, or WebP)<input key={fileInputKey} name="signed-file" className="mt-1 block w-full text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-foreground/5 file:px-3 file:py-2 file:text-xs" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
            <p className="text-xs text-muted-foreground">Maximum file size: 10 MB. The form version and wording are preserved with the record.</p>
            <Button type="submit" loading={busy} disabled={!options.length || !members.length}>Save signed record</Button>
          </form>
        </Card>
      </div>

      {canManage && memberId && <Card className="mt-5">
        <CardHeader title="Signed records" subtitle={members.find((member) => member.member_id === memberId)?.member_name ?? "Selected member"} />
        <div className="divide-y divide-foreground/10">
          {acceptances.map((record) => <div key={record.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
            <div><p className="text-sm font-medium">{record.form_title} <Badge tone="neutral">v{record.form_version}</Badge></p><p className="text-xs text-muted-foreground">Signed by {record.signed_by_name} · recorded {new Date(record.recorded_at).toLocaleString()}</p></div>
            <a className="text-sm font-medium text-brand hover:underline" href={`/api/download/gym-forms/acceptances/${record.id}/evidence`}>Review signed file ↗</a>
          </div>)}
          {!acceptances.length && <p className="px-5 py-4 text-sm text-muted-foreground">No signed forms recorded for this member.</p>}
        </div>
      </Card>}
      <p className="mt-5 text-xs text-muted-foreground">Form records support staff administration; they do not certify legal validity or replace professional medical review. <Link className="text-brand hover:underline" href="/app">Back to dashboard</Link></p>
    </main>
  );
}
