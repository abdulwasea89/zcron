"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import { Button, Select } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type ImportResult = { created: number; updated: number; skipped: number; errors: { row: number; error: string }[] };
type Preview = { headers: string[]; mapping: Record<string, string>; rows: { row: number; email: string; action: "add" | "existing" | "error"; fillable_fields: string[]; error: string | null }[] };
const fields = { email: "Email (required)", full_name: "Full name", first_name: "First name", last_name: "Last name", phone: "Phone" };

export function MemberImportSheet({ open, onOpenChange, onImported }: {
  open: boolean; onOpenChange: (open: boolean) => void; onImported: () => void | Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [fillMissing, setFillMissing] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const importKey = useRef("");
  const fileInput = useRef<HTMLInputElement>(null);

  function invalidate() { setPreview(null); setResult(null); importKey.current = ""; }
  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob(["email,full_name,phone\nmember@example.com,Alex Member,+15555550100\n"], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url; link.download = "member-import-template.csv"; link.click(); URL.revokeObjectURL(url);
  }
  async function submit(apply: boolean) {
    if (!file || busy) return;
    if (!/\.(csv|xlsx)$/i.test(file.name) || file.size > 2_000_000) {
      toast.error("Choose a CSV or .xlsx workbook up to 2 MB."); return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("column_mapping", headers.length ? JSON.stringify(mapping) : "null");
      if (apply) {
        if (!preview?.rows.length) return;
        form.append("fill_missing", String(fillMissing));
        importKey.current ||= crypto.randomUUID();
        const imported = await api.post<ImportResult>("/members/import", form, { "Idempotency-Key": importKey.current });
        setResult(imported); setFile(null); setPreview(null);
        if (fileInput.current) fileInput.current.value = "";
        toast.success(`Import finished: ${imported.created} added, ${imported.updated} updated.`);
        try { await onImported(); } catch { toast.error("Import finished. Reload the member list to see the changes."); }
      } else {
        const checked = await api.post<Preview>("/members/import/preview", form);
        setHeaders(checked.headers); setMapping(checked.mapping); setPreview(checked); setResult(null);
      }
    } catch (error) {
      toast.error((error as ApiError).message || "Could not process this import.");
    } finally { setBusy(false); }
  }
  const rows = preview?.rows ?? [];
  return <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent side="right" className="sm:max-w-[620px]">
      <SheetHeader><SheetTitle>Import members</SheetTitle><SheetDescription>Map CSV or Excel columns, review duplicates, then import. Excel uses the first worksheet.</SheetDescription></SheetHeader>
      <SheetBody className="space-y-5">
        <Button type="button" variant="secondary" onClick={downloadTemplate}>Download CSV template</Button>
        <div className="space-y-2">
          <label htmlFor="member-import-file" className="block text-xs font-medium">CSV or Excel · up to 2 MB</label>
          <input ref={fileInput} id="member-import-file" type="file" disabled={busy} accept=".csv,.xlsx" onChange={(event) => {
            setFile(event.target.files?.[0] ?? null); setHeaders([]); setMapping({}); invalidate();
          }} className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-2" />
        </div>
        {headers.length > 0 && <section className="grid gap-3 sm:grid-cols-2" aria-label="Column mapping">
          {Object.entries(fields).map(([field, label]) => <Select key={field} label={label} disabled={busy} value={mapping[field] || ""} onChange={(event) => {
            const next = { ...mapping }; if (event.target.value) next[field] = event.target.value; else delete next[field];
            setMapping(next); invalidate();
          }}><option value="">{field === "email" ? "Choose a column" : "Do not import"}</option>{headers.map((header) => <option key={header} value={header}>{header}</option>)}</Select>)}
        </section>}
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={fillMissing} disabled={busy} onChange={(event) => { setFillMissing(event.target.checked); importKey.current = ""; }} />
          Fill blank display names and phones on matching gym members. Existing values and shared account details are preserved; staff profiles are skipped.
        </label>
        <p className="text-xs leading-5 text-muted-foreground">New members are pending activation; an activation email is attempted. No plans, payments, consent, or roles are imported. Duplicate emails within the file need correction. Different email addresses are never merged automatically.</p>
        {preview && <section aria-live="polite" className="space-y-3 border border-border p-4">
          <h3 className="text-sm font-semibold">Preview · {rows.length} rows</h3>
          {rows.length === 0 ? <p className="text-sm">Choose an email column, then preview again.</p> : <>
            <p className="text-xs text-muted-foreground">{rows.filter((row) => row.action === "add").length} to add · {rows.filter((row) => row.action === "existing").length} existing · {rows.filter((row) => row.error).length} invalid</p>
            <ul className="max-h-64 space-y-2 overflow-y-auto text-xs">{rows.slice(0, 100).map((row) => <li key={row.row} className="break-words border-b border-border pb-2">
              Row {row.row} · {row.email || "No email"} — {row.error || (row.action === "add" ? "Add pending member" : fillMissing && row.fillable_fields.length ? `Fill missing ${row.fillable_fields.join(", ")}` : "Skip existing member")}
            </li>)}</ul>{rows.length > 100 && <p className="text-xs text-muted-foreground">Showing the first 100 rows; all rows are validated.</p>}
          </>}
        </section>}
        {result && <section aria-live="polite" className="space-y-3 border border-border p-4">
          <h3 className="text-sm font-semibold">Import finished</h3>
          <p className="text-sm">{result.created} added · {result.updated} updated · {result.skipped} skipped</p>
          <ul className="max-h-52 space-y-1 overflow-y-auto text-xs text-muted-foreground">{result.errors.map((error, index) => <li key={`${error.row}-${index}`}>Row {error.row}: {error.error}</li>)}</ul>
        </section>}
      </SheetBody>
      <SheetFooter><Button variant="secondary" disabled={busy} onClick={() => onOpenChange(false)}>Close</Button>
        <Button variant="secondary" disabled={!file || busy} onClick={() => void submit(false)}>Preview</Button>
        <Button disabled={!file || busy || !rows.some((row) => row.action !== "error")} loading={busy} onClick={() => void submit(true)}>Import reviewed rows</Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>;
}
