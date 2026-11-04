"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { TaskOut } from "@/lib/types";
import { DashboardWorkSheet } from "@/components/DashboardWorkSheet";
import { dashboardWork, type DashboardWork } from "@/lib/dashboard-work";
import { Check, ChevronRight, CircleCheck, EyeOff, ListPlus, LoaderCircle, MoreHorizontal, Phone, Pencil } from "lucide-react";
import { Button } from "@/components/ui";
import { DashboardEmptyState, DashboardRetry } from "@/components/DashboardUI";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export function DashboardTaskList({
  tasks,
  attention,
  storageKey,
  unavailable = false,
}: {
  tasks: (TaskOut & { dueLabel: string; overdue: boolean; dueToday: boolean })[];
  attention: { key: string; label: string; value: string; href: string; tone: "neutral" | "success" | "danger" | "warning" | "info"; phone?: string | null; member_id?: string; personName?: string | null; priority: number }[];
  storageKey: string;
  unavailable?: boolean;
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
  const [hidingKey, setHidingKey] = useState<string | null>(null);
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
    setHidingKey(key);
    try {
      const result = await api.post<{ keys: string[] }>("/analytics/dashboard/hidden-attention", { key });
      setHiddenKeys(result.keys);
      toast.success("Hidden from your dashboard.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not hide this alert.");
    } finally {
      setHidingKey(null);
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
  const visibleItems = showAll ? items : items.slice(0, 3);

  return <>
    <div className="dash-section-heading"><h2>Priorities</h2><span className="dash-badge" data-tone={items.length ? "warning" : "success"}>{items.length} open</span></div>
    {unavailable && <DashboardRetry>Tasks couldn’t load. Alerts below are still available.</DashboardRetry>}
    {items.length ? <ul className="dash-priorities">
      {visibleItems.map(item => {
        const action = dashboardWork(item);
        const busy = item.task ? completing === item.task.id : addingTaskFor === item.key || hidingKey === item.key;
        return <li key={item.id} className="dash-priority">
          <span className="dash-status-dot" data-tone={item.tone} aria-hidden="true" />
          <div className="dash-priority-copy">
            {action ? <button type="button" onClick={() => setWork(action)}>{item.label}</button> : <Link href={item.href}>{item.label}</Link>}
            <span className="dash-meta">{item.value}</span>
          </div>
          <div className="dash-row-actions">
            <Button variant="secondary" className="dash-button dash-secondary" disabled={busy} onClick={() => action ? setWork(action) : router.push(item.href)}>Open<ChevronRight aria-hidden="true" /></Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button variant="ghost" className="dash-button dash-ghost dash-icon-button" disabled={busy} aria-label={`More actions for ${item.label}`}>{busy ? <LoaderCircle className="animate-spin" aria-label="Saving" /> : <MoreHorizontal aria-hidden="true" />}</Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="dashboard-menu">
                {item.phone && <DropdownMenuItem asChild><a href={`tel:${item.phone}`}><Phone aria-hidden="true" />Call</a></DropdownMenuItem>}
                {item.task && canEditTasks && <DropdownMenuItem onSelect={() => setWork(action)}><Pencil aria-hidden="true" />Edit task</DropdownMenuItem>}
                {item.task && <DropdownMenuItem disabled={completing !== null} onSelect={() => void complete(item.task!)}><Check aria-hidden="true" />Mark complete</DropdownMenuItem>}
                {!item.task && canEditTasks && <DropdownMenuItem disabled={addingTaskFor !== null} onSelect={() => void createFollowUpTask(item)}><ListPlus aria-hidden="true" />Add task</DropdownMenuItem>}
                {!item.task && <DropdownMenuItem onSelect={() => void hideAttention(item.key)}><EyeOff aria-hidden="true" />Hide from dashboard</DropdownMenuItem>}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </li>;
      })}
    </ul> : !unavailable && <DashboardEmptyState icon={<CircleCheck />} title="You’re all caught up" href="/app/tasks" action="View tasks">Your tasks and follow-ups will appear here when they need attention.</DashboardEmptyState>}
    <div className="dash-task-footer">
      {items.length > 3 && <Button variant="ghost" className="dash-button dash-ghost" aria-expanded={showAll} onClick={() => setShowAll(value => !value)}>{showAll ? "Show fewer" : `View all ${items.length}`}<ChevronRight aria-hidden="true" /></Button>}
      <Link href="/app/tasks" className="dash-button dash-ghost">All tasks<ChevronRight aria-hidden="true" /></Link>
      {attention.length > 0 && <Link href="/app/approvals" className="dash-button dash-ghost">Review queue<ChevronRight aria-hidden="true" /></Link>}
      {hiddenKeys.length > 0 && <Button variant="ghost" className="dash-button dash-ghost" disabled={restoringHidden} loading={restoringHidden} onClick={() => void restoreHidden()}>Restore hidden ({hiddenKeys.length})</Button>}
    </div>
    <DashboardWorkSheet work={work} onClose={() => { setWork(null); router.refresh(); }} />
  </>;
}
