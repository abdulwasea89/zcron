export type DashboardWork = {
  kind: "tasks" | "receipts" | "approvals" | "leads" | "retention";
  title: string;
  taskId?: string;
  memberId?: string;
};

export function dashboardWork(item: { label: string; href: string; member_id?: string; task?: { id: string } | null }): DashboardWork | null {
  if (item.task) return { kind: "tasks", title: item.label, taskId: item.task.id };
  if (item.member_id) return { kind: "retention", title: item.label, memberId: item.member_id };
  const path = item.href.split("?")[0];
  const kind = path === "/app/receipts" ? "receipts" : path === "/app/approvals" ? "approvals"
    : path === "/app/leads" ? "leads" : path === "/app/retention" ? "retention" : null;
  return kind ? { kind, title: item.label } : null;
}

export function isRecentUntouchedLead(lead: { first_contact_logged: boolean; stage: string; created_at: string }, since: number): boolean {
  const createdAt = /Z$|[+-]\d{2}:\d{2}$/.test(lead.created_at) ? lead.created_at : `${lead.created_at}Z`;
  return !lead.first_contact_logged && !["joined", "lost"].includes(lead.stage) && Date.parse(createdAt) >= since;
}
