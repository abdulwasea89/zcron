"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { TaskOut } from "@/lib/types";
import { DashboardWorkSheet } from "@/components/DashboardWorkSheet";
import { dashboardWork, type DashboardWork } from "@/lib/dashboard-work";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export function DashboardTaskList({
  tasks,
  attention,
  storageKey,
}: {
  tasks: (TaskOut & { dueLabel: string; overdue: boolean; dueToday: boolean })[];
  attention: { key: string; label: string; value: string; href: string; tone: "neutral" | "success" | "danger" | "warning" | "info"; phone?: string | null; member_id?: string; personName?: string | null; priority: number }[];
  storageKey: string;
}) {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const canEditTasks = ["owner", "manager", "trainer"].includes(currentUser?.role ?? "");
  const [work, setWork] = useState<DashboardWork | null>(null);
  const [openTasks, setOpenTasks] = useState(tasks);
  const [completing, setCompleting] = useState<string | null>(null);
  const [addingTaskFor, setAddingTaskFor] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [hiddenKeys, setHiddenKeys] = useState<string[]>([]);
  const [restoringHidden, setRestoringHidden] = useState(false);

  useEffect(() => {
    let active = true;
    api.get<{ keys: string[] }>("/analytics/dashboard/hidden-attention")
      .then((result) => { if (active) setHiddenKeys(result.keys); })
      .catch(() => {});
    return () => { active = false; };
  }, [storageKey]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setOpenTasks(tasks));
    return () => cancelAnimationFrame(frame);
  }, [tasks]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setShowAll(false));
    return () => cancelAnimationFrame(frame);
  }, [storageKey]);

  async function complete(task: TaskOut) {
    setCompleting(task.id);
    try {
      await api.post(`/staff/tasks/${task.id}/complete`);
      setOpenTasks((current) => current.filter((item) => item.id !== task.id));
      toast.success("Task completed.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not complete this task.");
    } finally {
      setCompleting(null);
    }
  }

  async function createFollowUpTask(item: (typeof attention)[number]) {
    if (addingTaskFor) return;
    setAddingTaskFor(item.key);
    try {
      const created = await api.post<TaskOut>("/staff/tasks", {
        title: (item.member_id ? `Follow up: ${item.personName || "member"}` : item.label).slice(0, 120),
        description: `${item.label} (${item.value}). Open: ${item.href}`.slice(0, 500),
        deadline: new Date().toISOString(),
      });
      setOpenTasks((current) => [{
        ...created,
        dueLabel: "Due today",
        overdue: false,
        dueToday: true,
      }, ...current]);
      toast.success("Follow-up task added to the team queue.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not create follow-up task.");
    } finally {
      setAddingTaskFor(null);
    }
  }

  async function hideAttention(key: string) {
    try {
      const result = await api.post<{ keys: string[] }>("/analytics/dashboard/hidden-attention", { key });
      setHiddenKeys(result.keys);
      toast.success("Hidden from your dashboard.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not hide this alert.");
    }
  }

  async function restoreHidden() {
    setRestoringHidden(true);
    try {
      await api.del("/analytics/dashboard/hidden-attention");
      setHiddenKeys([]);
      toast.success("Hidden alerts restored.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not restore hidden alerts.");
    } finally {
      setRestoringHidden(false);
    }
  }

  const items = [
    ...openTasks.map((task) => ({
      id: `task:${task.id}`,
      label: task.title,
      value: task.dueLabel,
      href: "/app/tasks",
      tone: task.overdue ? "danger" as const : task.dueToday ? "warning" as const : "neutral" as const,
      priority: task.overdue ? 0 : task.dueToday ? 2 : task.deadline ? 5 : 7,
      phone: null,
      member_id: undefined,
      personName: undefined,
      task,
    })),
    ...attention.filter((item) => !hiddenKeys.includes(item.key)).map((item) => ({ ...item, id: `attention:${item.key}`, task: null })),
  ].sort((a, b) => a.priority - b.priority || a.label.localeCompare(b.label));
  const visibleItems = showAll ? items : items.slice(0, 6);

  return (
    <div className="px-4 py-2">
      {items.length ? (
        <ul className="m-0 list-none divide-y divide-border p-0">
          {visibleItems.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-[12px]">
              {dashboardWork(item) ? <button type="button" onClick={() => setWork(dashboardWork(item))} className="min-w-0 truncate text-left font-medium text-foreground hover:text-brand">{item.label}</button> : <Link href={item.href} className="min-w-0 truncate font-medium text-foreground no-underline hover:text-brand">{item.label}</Link>}
              <span className="flex shrink-0 items-center gap-2">
                <span className={item.tone === "danger" ? "text-danger" : item.tone === "warning" ? "text-warning" : "text-muted-foreground"}>
                  {item.value}
                </span>
                {item.phone && <a href={`tel:${item.phone}`} className="text-brand no-underline hover:underline">Call</a>}
                {item.task && canEditTasks && <button
                  type="button"
                  onClick={() => setWork(dashboardWork(item))}
                  className="text-brand no-underline hover:underline"
                  aria-label={`Edit ${item.task.title}`}
                >Edit</button>}
                {!item.task && canEditTasks && <button
                  type="button"
                  disabled={addingTaskFor !== null}
                  onClick={() => void createFollowUpTask(item)}
                  className="text-brand no-underline hover:underline disabled:opacity-50"
                  aria-label={`Create follow-up task for ${item.label}`}
                >{addingTaskFor === item.key ? "Adding…" : "Add task"}</button>}
                {!item.task && <button type="button" onClick={() => void hideAttention(item.key)} className="text-muted-foreground hover:text-foreground" aria-label={`Hide ${item.label} from your dashboard`}>Hide</button>}
                {!item.task && <button
                  type="button"
                  onClick={() => {
                    const action = dashboardWork(item);
                    if (action) setWork(action);
                    else router.push(item.href);
                  }}
                  className="text-brand no-underline hover:underline"
                >Open</button>}
                {item.task && <button
                  type="button"
                  aria-label={`Mark ${item.task.title} complete`}
                  title="Mark complete"
                  disabled={completing !== null}
                  onClick={() => void complete(item.task!)}
                  className="inline-flex h-7 w-7 items-center justify-center border border-border text-muted-foreground transition-colors hover:border-success hover:text-success disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="m5 12 4 4L19 6" />
                  </svg>
                </button>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-2 text-[12px] text-muted-foreground">You’re clear. Nothing needs attention today.</p>
      )}
      <div className="flex gap-3 border-t border-border pt-2 text-[11px]">
        {items.length > 6 && <button type="button" aria-expanded={showAll} onClick={() => setShowAll((value) => !value)} className="font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">{showAll ? "Show fewer" : `Show all ${items.length}`}</button>}
        <Link href="/app/tasks" className="font-medium text-brand no-underline hover:underline">All tasks ↗</Link>
        {attention.length > 0 && <Link href="/app/approvals" className="font-medium text-brand no-underline hover:underline">Review queue ↗</Link>}
        {hiddenKeys.length > 0 && <button type="button" disabled={restoringHidden} onClick={() => void restoreHidden()} className="font-medium text-brand hover:underline disabled:opacity-50">{restoringHidden ? "Restoring…" : `Restore hidden alerts (${hiddenKeys.length})`}</button>}
      </div>
      <DashboardWorkSheet work={work} onClose={() => { setWork(null); router.refresh(); }} />
    </div>
  );
}
