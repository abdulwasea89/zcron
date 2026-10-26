import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/dashboard-work.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const moduleOutput = { exports: {} };
vm.runInNewContext(code, { module: moduleOutput, exports: moduleOutput.exports });
const { dashboardWork, isRecentUntouchedLead } = moduleOutput.exports;
for (const [route, kind] of [["receipts", "receipts"], ["approvals", "approvals"], ["leads", "leads"], ["retention", "retention"]]) {
  assert.equal(dashboardWork({ label: "Priority", href: `/app/${route}?from=dashboard` }).kind, kind);
}
assert.equal(dashboardWork({ label: "Member", href: "/app/members", member_id: "member" }).memberId, "member");
assert.equal(dashboardWork({ label: "Task", href: "/app/tasks", task: { id: "task" } }).taskId, "task");
assert.equal(dashboardWork({ label: "Other", href: "/app/invoices" }), null);
assert.equal(dashboardWork({ label: "Other", href: "/app/leads-unrelated" }), null);
const cutoff = Date.parse("2026-01-01T00:00:00Z");
const lead = { first_contact_logged: false, stage: "new", created_at: "2026-01-01T00:00:00" };
assert.equal(isRecentUntouchedLead(lead, cutoff), true);
assert.equal(isRecentUntouchedLead({ ...lead, created_at: "2026-01-01T05:00:00+05:00" }, cutoff), true);
assert.equal(isRecentUntouchedLead({ ...lead, created_at: "2025-12-31T23:59:59Z" }, cutoff), false);
assert.equal(isRecentUntouchedLead({ ...lead, stage: "joined" }, cutoff), false);
assert.equal(isRecentUntouchedLead({ ...lead, first_contact_logged: true }, cutoff), false);
assert.equal(isRecentUntouchedLead({ ...lead, created_at: "invalid" }, cutoff), false);
console.log("Dashboard priority routing checks passed.");
