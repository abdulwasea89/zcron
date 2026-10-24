"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { TaskOut } from "@/lib/types";

export function DashboardTaskList({
  tasks,
  attention,
}: {
  tasks: (TaskOut & { dueLabel: string; overdue: boolean; dueToday: boolean })[];
  attention: { label: string; value: string; href: string; tone: "neutral" | "success" | "danger" | "warning" | "info"; phone?: string | null; member_id?: string; personName?: string | null; priority: number }[];
}) {
  const [openTasks, setOpenTasks] = useState(tasks);
  const [completing, setCompleting] = useState<string | null>(null);
  const [addingTaskFor, setAddingTaskFor] = useState<string | null>(null);
  const [taskCreatedFor, setTaskCreatedFor] = useState<Set<string>>(new Set());

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
    if (!item.member_id || addingTaskFor) return;
    setAddingTaskFor(item.member_id);
    try {
      const created = await api.post<TaskOut>("/staff/tasks", {
        title: `Follow up: ${item.personName || "member"}`,
        description: `${item.label} (${item.value}). Open member: ${item.href}`,
        deadline: new Date().toISOString(),
      });
      setOpenTasks((current) => [{
        ...created,
        dueLabel: "Due today",
        overdue: false,
        dueToday: true,
      }, ...current]);
      setTaskCreatedFor((current) => new Set(current).add(item.member_id!));
      toast.success("Follow-up task added to the team queue.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not create follow-up task.");
    } finally {
      setAddingTaskFor(null);
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
    ...attention.filter((item) => !item.member_id || !taskCreatedFor.has(item.member_id)).map((item, index) => ({ ...item, id: `attention:${index}:${item.label}`, task: null })),
  ].sort((a, b) => a.priority - b.priority || a.label.localeCompare(b.label)).slice(0, 6);

  return (
    <div className="px-4 py-2">
      {items.length ? (
        <ul className="m-0 list-none divide-y divide-border p-0">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-[12px]">
              <Link href={item.href} className="min-w-0 truncate font-medium text-foreground no-underline hover:text-brand">{item.label}</Link>
              <span className="flex shrink-0 items-center gap-2">
                <span className={item.tone === "danger" ? "text-danger" : item.tone === "warning" ? "text-warning" : "text-muted-foreground"}>
                  {item.value}
                </span>
                {item.phone && <a href={`tel:${item.phone}`} className="text-brand no-underline hover:underline">Call</a>}
                {item.member_id && <button
                  type="button"
                  disabled={addingTaskFor !== null}
                  onClick={() => void createFollowUpTask(item)}
                  className="text-brand no-underline hover:underline disabled:opacity-50"
                >{addingTaskFor === item.member_id ? "Adding…" : "Add task"}</button>}
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
        <Link href="/app/tasks" className="font-medium text-brand no-underline hover:underline">All tasks ↗</Link>
        {attention.length > 0 && <Link href="/app/approvals" className="font-medium text-brand no-underline hover:underline">Review queue ↗</Link>}
      </div>
    </div>
  );
}
