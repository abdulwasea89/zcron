"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { TaskOut } from "@/lib/types";

export function DashboardTaskList({
  tasks,
}: {
  tasks: (TaskOut & { dueLabel: string; overdue: boolean; dueToday: boolean })[];
}) {
  const [openTasks, setOpenTasks] = useState(tasks);
  const [completing, setCompleting] = useState<string | null>(null);

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

  return (
    <div className="border-b border-border px-4 py-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold">Open team tasks</h3>
        <Link href="/app/tasks" className="text-[11px] font-medium text-brand no-underline hover:underline">View tasks ↗</Link>
      </div>
      {openTasks.length ? (
        <ul className="m-0 list-none divide-y divide-border p-0">
          {openTasks.slice(0, 4).map((task) => (
            <li key={task.id} className="flex items-center justify-between gap-3 py-2 text-[12px]">
              <span className="min-w-0 truncate font-medium">{task.title}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span className={task.overdue ? "text-danger" : task.dueToday ? "text-warning" : "text-muted-foreground"}>
                  {task.dueLabel}
                </span>
                <button
                  type="button"
                  aria-label={`Mark ${task.title} complete`}
                  title="Mark complete"
                  disabled={completing !== null}
                  onClick={() => void complete(task)}
                  className="inline-flex h-7 w-7 items-center justify-center border border-border text-muted-foreground transition-colors hover:border-success hover:text-success disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="m5 12 4 4L19 6" />
                  </svg>
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[12px] text-muted-foreground">You’re clear. No open tasks.</p>
      )}
    </div>
  );
}
