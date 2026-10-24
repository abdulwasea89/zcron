"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type ImportResult = { created: number; skipped: number; errors: { row: number; error: string }[] };

export function MemberImportSheet({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void | Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob(["email,full_name,phone\nmember@example.com,Alex Member,+15555550100\n"], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "member-import-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    if (!/\.(csv|xlsx)$/i.test(file.name)) {
      toast.error("Choose a CSV or .xlsx workbook.");
      return;
    }
    if (file.size > 2_000_000) {
      toast.error("Import files must be 2 MB or smaller.");
      return;
    }

    setBusy(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const imported = await api.post<ImportResult>("/members/import", form);
      setResult(imported);
      setFile(null);
      await onImported();
    } catch (error) {
      toast.error((error as ApiError).message || "Could not import members.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-[520px]">
        <SheetHeader>
          <SheetTitle>Import members</SheetTitle>
          <SheetDescription>Upload a CSV or Excel workbook to add members to this workspace. Excel imports use the first worksheet.</SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-5">
          <section className="space-y-2 text-sm">
            <p className="text-foreground">Use a header row with <code>email</code>, <code>full_name</code>, and <code>phone</code>. Email is required; the other columns are optional.</p>
            <Button type="button" variant="secondary" onClick={downloadTemplate}>Download CSV template</Button>
          </section>

          <p className="border border-border bg-background/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
            New rows are created as pending activation and an activation email is attempted. Existing workspace members are skipped. Delivery failures and invalid rows are included in the results.
          </p>

          <form id="member-import-form" onSubmit={(event) => void submit(event)} className="space-y-3">
            <label htmlFor="member-import-file" className="block text-xs font-medium text-foreground">CSV or Excel workbook · up to 2 MB</label>
            <input
              id="member-import-file"
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={busy}
              onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); }}
              className="block w-full text-sm text-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-xs file:text-foreground"
            />
            {file && <p className="text-xs text-muted-foreground">{file.name} · {(file.size / 1024).toFixed(1)} KB</p>}
          </form>

          {result && <section aria-live="polite" className="space-y-3 border border-border p-4">
            <h3 className="text-sm font-semibold">Import complete</h3>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-muted-foreground">Added</dt><dd className="font-medium">{result.created}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Skipped</dt><dd className="font-medium">{result.skipped}</dd></div>
            </dl>
            {result.errors.length > 0 && <div>
              <p className="mb-2 text-xs font-medium text-warning">Needs attention · {result.errors.length}</p>
              <ul className="max-h-40 space-y-1 overflow-y-auto text-xs text-muted-foreground">
                {result.errors.slice(0, 20).map((error, index) => <li key={`${error.row}-${index}`}>Row {error.row}: {error.error}</li>)}
              </ul>
              {result.errors.length > 20 && <p className="mt-2 text-xs text-muted-foreground">Showing the first 20 issues.</p>}
            </div>}
          </section>}
        </SheetBody>
        <SheetFooter>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => onOpenChange(false)}>Close</Button>
          <Button type="submit" form="member-import-form" disabled={!file || busy} loading={busy}>Import members</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
