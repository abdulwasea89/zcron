"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Avatar, Badge, Button, EmptyState, Input, Spinner, Textarea } from "@/components/ui";
import { FieldSelect, NONE } from "@/components/FieldSelect";
import { SelectItem } from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ListToolbar } from "@/components/ListToolbar";
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { api, ApiError } from "@/lib/api";
import { dateKeyInTimeZone } from "@/lib/format";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import type { OrganizationOut, TaskOut, MemberDirectoryItem } from "@/lib/types";

export default function TasksPage() {
  const currentUser = useCurrentUser();
  const isTrainer = currentUser?.role === "trainer";
  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [timeZone, setTimeZone] = useState("UTC");
  const [members, setMembers] = useState<MemberDirectoryItem[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "completed">("all");
  const [search, setSearch] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState(NONE);
  const [deadlineFilter, setDeadlineFilter] = useState(NONE);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<TaskOut | null>(null);
  const [deleting, setDeleting] = useState<TaskOut | null>(null);
  const [viewing, setViewing] = useState<TaskOut | null>(null);
  const [menuTask, setMenuTask] = useState<TaskOut | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
  const editDeepLinkHandled = useRef(false);

  // Create form state
  const [formTitle, setFormTitle] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formAssignee, setFormAssignee] = useState("");
  const [formDeadline, setFormDeadline] = useState("");
  const [formError, setFormError] = useState("");
  const [formLoading, setFormLoading] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const t = await api.get<TaskOut[]>("/staff/tasks");
      setTasks(t);
      if (!editDeepLinkHandled.current) {
        const taskId = new URLSearchParams(window.location.search).get("edit");
        const task = taskId ? t.find((item) => item.id === taskId) : null;
        if (task) {
          editDeepLinkHandled.current = true;
          setEditing(task);
          setFormTitle(task.title);
          setFormDesc(task.description || "");
          setFormAssignee(task.assignee_member_id || "");
          setFormDeadline(task.deadline ? task.deadline.slice(0, 10) : "");
          setShowForm(true);
        }
      }
    } catch (e) {
      setError((e as ApiError).message);
      setTasks([]);
    }
    try {
      const org = await api.get<OrganizationOut>("/organizations/me");
      setTimeZone(org.timezone || "UTC");
    } catch {
      // Keep UTC as the fallback if workspace settings are unavailable.
    }
    try {
      const m = await api.get<MemberDirectoryItem[]>("/members");
      setMembers(m);
    } catch {
      // Members fetch is best-effort for the assignee dropdown
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  const memberById = Object.fromEntries(
    members.map((m) => [m.member_id, m.full_name || m.email]),
  );
  const todayKey = dateKeyInTimeZone(new Date(), timeZone);

  const q = search.trim().toLowerCase();
  const filtered = (tasks ?? []).filter((t) => {
    if (filter === "active" && t.done) return false;
    if (filter === "completed" && !t.done) return false;
    const assignee = t.assignee_member_id ? memberById[t.assignee_member_id] ?? "" : "";
    const matchesSearch = !q || t.title.toLowerCase().includes(q) || (t.description ?? "").toLowerCase().includes(q) || assignee.toLowerCase().includes(q);
    const matchesAssignee = assigneeFilter === NONE || (assigneeFilter === "__unassigned__" ? !t.assignee_member_id : t.assignee_member_id === assigneeFilter);
    const dueKey = t.deadline?.slice(0, 10) ?? null;
    const daysUntilDue = dueKey
      ? (Date.parse(`${dueKey}T00:00:00Z`) - Date.parse(`${todayKey}T00:00:00Z`)) / 86_400_000
      : null;
    const matchesDeadline = deadlineFilter === NONE ||
      (deadlineFilter === "overdue" ? Boolean(!t.done && daysUntilDue !== null && daysUntilDue < 0) :
        deadlineFilter === "week" ? Boolean(!t.done && daysUntilDue !== null && daysUntilDue >= 0 && daysUntilDue <= 7) :
          deadlineFilter === "no_deadline" ? !dueKey : Boolean(!t.done && daysUntilDue !== null && daysUntilDue > 7));
    return matchesSearch && matchesAssignee && matchesDeadline;
  });
  const activeTaskFilterCount = [assigneeFilter, deadlineFilter].filter((v) => v !== NONE).length;
  function clearTaskFilters() { setAssigneeFilter(NONE); setDeadlineFilter(NONE); }

  // Create task
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    setFormLoading(true);
    try {
      await api.post("/staff/tasks", {
        title: formTitle,
        description: formDesc || null,
        assignee_member_id: formAssignee || null,
        deadline: formDeadline || null,
      });
      resetForm();
      load();
    } catch (e) {
      setFormError((e as ApiError).message);
    } finally {
      setFormLoading(false);
    }
  }

  // Update task
  async function update(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setFormError("");
    setFormLoading(true);
    try {
      await api.patch(`/staff/tasks/${editing.id}`, {
        title: formTitle,
        description: formDesc || null,
        assignee_member_id: formAssignee || null,
        deadline: formDeadline || null,
      });
      setEditing(null);
      resetForm();
      load();
    } catch (e) {
      setFormError((e as ApiError).message);
    } finally {
      setFormLoading(false);
    }
  }

  // Delete task
  async function confirmDelete() {
    if (!deleting) return;
    setError("");
    try {
      await api.del(`/staff/tasks/${deleting.id}`);
      setDeleting(null);
      load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  function resetForm() {
    setFormTitle("");
    setFormDesc("");
    setFormAssignee("");
    setFormDeadline("");
    setShowForm(false);
    setEditing(null);
    setFormError("");
  }

  function openEdit(task: TaskOut) {
    setEditing(task);
    setFormTitle(task.title);
    setFormDesc(task.description || "");
    setFormAssignee(task.assignee_member_id || "");
    setFormDeadline(task.deadline ? task.deadline.slice(0, 10) : "");
    setShowForm(true);
  }

  useEffect(() => {
    if (!menuTask) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeMenu(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [menuTask]);

  function closeMenu() { setMenuTask(null); setMenuPos(null); }

  function openMenu(task: TaskOut, e: React.MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setMenuPos({ top: rect.bottom + 4, right: document.documentElement.clientWidth - rect.right });
    setMenuTask(task);
  }

  async function markDone(task: TaskOut) {
    if (task.done) return;
    setError("");
    const prev = tasks;
    setTasks((t) => (t ?? []).map((x) => (x.id === task.id ? { ...x, done: true } : x)));
    try {
      await api.post(`/staff/tasks/${task.id}/complete`);
    } catch (e) {
      setTasks(prev);
      setError((e as ApiError).message);
    }
  }

  const tabs = [
    { value: "all" as const, label: "All", count: (tasks ?? []).length },
    { value: "active" as const, label: "Active", count: (tasks ?? []).filter((t) => !t.done).length },
    { value: "completed" as const, label: "Completed", count: (tasks ?? []).filter((t) => t.done).length },
  ];

  return (
    <>
      <PageHeader
        title="Tasks"
        subtitle="Simple task management for your team"
        action={
          <Button onClick={() => { resetForm(); setShowForm(true); }}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            New task
          </Button>
        }
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {/* Create / edit lives in a sheet, not a centred modal: it is about the task
          list behind it, so the list stays in view while you fill it in. */}
      <Sheet open={showForm} onOpenChange={resetForm}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div>
              <SheetTitle>{editing ? "Edit task" : "New task"}</SheetTitle>
              <SheetDescription>
                {editing ? "Update task details" : isTrainer ? "Create a task assigned to you" : "Assign a task to a team member"}
              </SheetDescription>
            </div>
          </SheetHeader>
          {/* `flex` + the form filling the sheet: header and footer stay put,
              only the fields scroll. */}
          <form onSubmit={editing ? update : submit} className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {formError && <Alert>{formError}</Alert>}
              <Input
                label="Title"
                required
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="What needs to be done?"
              />
              {isTrainer ? (
                <p className="text-sm text-muted-foreground">Assigned to you</p>
              ) : (
                <FieldSelect
                  label="Assignee"
                  value={formAssignee || NONE}
                  onChange={(v) => setFormAssignee(v === NONE ? "" : v)}
                >
                  <SelectItem value={NONE}>Unassigned</SelectItem>
                  {members.map((m) => (
                    <SelectItem key={m.member_id} value={m.member_id}>
                      {m.full_name || m.email}
                    </SelectItem>
                  ))}
                </FieldSelect>
              )}
              <Input label="Deadline" type="date" value={formDeadline} onChange={(e) => setFormDeadline(e.target.value)} />
              <Textarea label="Description" value={formDesc} onChange={(e) => setFormDesc(e.target.value)} placeholder="Optional details, notes, or instructions" rows={3} />
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button type="button" variant="secondary" onClick={resetForm}>Cancel</Button>
              </SheetClose>
              <Button type="submit" loading={formLoading}>{editing ? "Save changes" : "Create task"}</Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      {/* Deleting is destructive, so it gets a centred AlertDialog: two answers,
          and it should stop you. */}
      <AlertDialog open={!!deleting} onOpenChange={(open) => { if (!open) setDeleting(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Delete task</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete <strong className="text-foreground">{deleting?.title}</strong>? This
            action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Cancel</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmDelete}>Delete task</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Detail view rides in a sheet too, so View and Edit both open the same
          surface beside the task list instead of a modal that hides it. */}
      <Sheet open={!!viewing} onOpenChange={(open) => { if (!open) setViewing(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>{viewing?.title ?? ""}</SheetTitle>
              <SheetDescription>Task details</SheetDescription>
            </div>
          </SheetHeader>
          <SheetBody className="space-y-5">
            {viewing && (
              <>
                {viewing.description && (
                  <div>
                    <span className="mb-1.5 block text-[12px] font-medium text-[var(--foreground)]">Description</span>
                    <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-[var(--foreground-muted)]">{viewing.description}</p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="mb-1 block text-[12px] font-medium text-[var(--foreground)]">Assignee</span>
                    <span className="text-sm text-[var(--foreground-muted)]">
                      {viewing.assignee_member_id ? (memberById[viewing.assignee_member_id] || "—") : "Unassigned"}
                    </span>
                  </div>
                  <div>
                    <span className="mb-1 block text-[12px] font-medium text-[var(--foreground)]">Deadline</span>
                    <span className="text-sm text-[var(--foreground-muted)]">
                      {viewing.deadline ? formatDate(viewing.deadline, timeZone) : "No deadline"}
                    </span>
                  </div>
                </div>
                <div>
                  <span className="mb-1 block text-[12px] font-medium text-[var(--foreground)]">Status</span>
                  <Badge tone={viewing.done ? "success" : "neutral"}>{viewing.done ? "Done" : "Active"}</Badge>
                </div>
              </>
            )}
          </SheetBody>
          <SheetFooter>
            {viewing && (
              <Button type="button" variant="primary" onClick={() => { setViewing(null); openEdit(viewing); }}>Edit</Button>
            )}
            <SheetClose asChild>
              <Button type="button" variant="secondary">Close</Button>
            </SheetClose>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <ListToolbar
        tabs={tabs}
        value={filter}
        onChange={setFilter}
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Search tasks…"
      >
          <ListFilterSheet title="Filter tasks" description="Focus on ownership and upcoming deadlines." activeCount={activeTaskFilterCount} resultCount={filtered.length} onClear={clearTaskFilters}>
            <FieldSelect label="Assigned to" value={assigneeFilter} onChange={setAssigneeFilter}>
              <SelectItem value={NONE}>Anyone</SelectItem><SelectItem value="__unassigned__">Unassigned</SelectItem>
              {members.map((member) => <SelectItem key={member.member_id} value={member.member_id}>{member.display_name || member.full_name || member.email}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Deadline" value={deadlineFilter} onChange={setDeadlineFilter}>
              <SelectItem value={NONE}>Any deadline</SelectItem><SelectItem value="overdue">Overdue</SelectItem><SelectItem value="week">Due in the next 7 days</SelectItem><SelectItem value="later">Due later</SelectItem><SelectItem value="no_deadline">No deadline</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
      </ListToolbar>

      {/* Flat workspace, not a card: rows are held by hairlines. */}
      <div className="mt-3">
        {tasks === null ? (
          <Spinner label="Loading tasks..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title={search || activeTaskFilterCount ? "No matching tasks" : "No tasks found"}
            hint={search || activeTaskFilterCount ? "Adjust your search or filters and try again." : filter !== "all" ? "Try a different status tab." : "Create your first task to get started."}
            action={filter === "all" && !search && !activeTaskFilterCount ? <Button onClick={() => { resetForm(); setShowForm(true); }}>+ New task</Button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST} w-12`} />
                  <th className={`${TH} ${CELL}`}>Title</th>
                  <th className={`${TH} ${CELL}`}>Assignee</th>
                  <th className={`${TH} ${CELL}`}>Deadline</th>
                  <th className={`${TH} ${CELL}`}>Status</th>
                  <th className={`${TH} ${CELL_LAST} text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((task) => {
                  const overdue = task.deadline && !task.done && task.deadline.slice(0, 10) < todayKey;
                  return (
                    <tr
                      key={task.id}
                      className={`${TR} transition-colors hover:bg-foreground/[0.02] ${task.done ? "opacity-50" : ""}`}
                    >
                      <td className={`${TD} ${CELL_FIRST} py-2.5`}>
                        <button
                          type="button"
                          disabled={task.done}
                          onClick={() => markDone(task)}
                          className={`flex h-5 w-5 items-center justify-center rounded border-2 transition-colors ${
                            task.done
                              ? "border-[var(--success)] bg-[var(--success)] text-white"
                              : "border-[var(--border-strong)] hover:border-[var(--primary)] hover:bg-[var(--primary-light)] cursor-pointer"
                          }`}
                          title={task.done ? "Completed" : "Mark as done"}
                        >
                          {task.done && (
                            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M4.5 12.75l6 6 9-13.5" />
                            </svg>
                          )}
                        </button>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5 max-w-[260px] font-medium ${task.done ? "text-[var(--muted)] line-through" : "text-[var(--foreground)]"}`}>
                        <button type="button" onClick={() => setViewing(task)} className="block w-full truncate text-left hover:underline">
                          {task.title}
                        </button>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        {task.assignee_member_id ? (
                          <div className="flex items-center gap-2">
                            <Avatar name={memberById[task.assignee_member_id] || "?"} size="sm" />
                            <span className="text-[var(--foreground-muted)]">
                              {memberById[task.assignee_member_id] || "—"}
                            </span>
                          </div>
                        ) : (
                          <span className="text-[var(--muted)]">Unassigned</span>
                        )}
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        {task.deadline ? (
                          <span className={`tabular-nums ${overdue ? "font-medium text-[var(--danger)]" : "text-[var(--foreground-muted)]"}`}>
                            {formatDate(task.deadline, timeZone)}
                          </span>
                        ) : (
                          <span className="text-[var(--muted)]">—</span>
                        )}
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <Badge tone={task.done ? "success" : "neutral"}>{task.done ? "Done" : "Active"}</Badge>
                      </td>
                      <td className={`${TD} ${CELL_LAST} py-2.5`}>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={(e) => openMenu(task, e)}
                            className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted)] transition-colors hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                          >
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                              <circle cx="12" cy="5" r="1.5" />
                              <circle cx="12" cy="12" r="1.5" />
                              <circle cx="12" cy="19" r="1.5" />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Portal-based kebab menu */}
      {menuTask && menuPos && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={closeMenu} />
          <div
            className="fixed z-50 min-w-[140px] animate-pop-in overflow-hidden rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10"
            style={{ top: menuPos.top, right: menuPos.right }}
          >
              <button
                type="button"
                onClick={() => { closeMenu(); setViewing(menuTask); }}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
              >
                <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                View
              </button>
              <button
                type="button"
                onClick={() => { closeMenu(); openEdit(menuTask); }}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
              >
                <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                </svg>
                Edit
              </button>
              <button
                type="button"
                onClick={() => { closeMenu(); setDeleting(menuTask); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--danger)] transition-colors hover:bg-danger-bg"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
              </svg>
              Delete
            </button>
          </div>
        </>,
        document.body,
      )}
    </>
  );
}

function formatDate(dateStr: string, timeZone: string): string {
  const dayKey = dateStr.slice(0, 10);
  const todayKey = dateKeyInTimeZone(new Date(), timeZone);
  const daysUntilDue = (Date.parse(`${dayKey}T00:00:00Z`) - Date.parse(`${todayKey}T00:00:00Z`)) / 86_400_000;
  if (daysUntilDue === 0) return "Today";
  if (daysUntilDue === 1) return "Tomorrow";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
    .format(new Date(`${dayKey}T00:00:00Z`));
}
