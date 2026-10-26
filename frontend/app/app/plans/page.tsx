"use client";

import { Fragment, useCallback, useEffect, useState, useMemo, type ReactNode } from "react";
import { useRealtimeEvent } from "@/components/Realtime";
import { PageHeader } from "@/components/PageHeader";
import { Glyph } from "@/components/Glyph";
import { TABLE, THEAD_ROW, TH, TR, TR_INTERACTIVE, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { ListToolbar } from "@/components/ListToolbar";
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { NONE } from "@/components/FieldSelect";
import { RowMenu } from "@/components/RowMenu";
import { PlanFields } from "@/components/plans/PlanFields";
import { PromotionsPanel } from "@/components/plans/PromotionsPanel";
import { useAssistantDock, useAssistantHint } from "@/components/assistant/AssistantDock";
import { useAssistantChats } from "@/components/assistant/AssistantChats";
import { Alert, Badge, Button, EmptyState, Input, Spinner, Textarea } from "@/components/ui";
import {
  Select as RadixSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { api, ApiError } from "@/lib/api";
import { money, statusTone, titleCase } from "@/lib/format";
import { buildPlanSummaryPrompt, planCadence, planStatusLabel } from "@/lib/plans";
import type { OrganizationOut, PlanOut } from "@/lib/types";
import { getIndustry } from "@/lib/industries";

/* ── Icons ────────────────────────────────────────────────────────────────
   One stroke voice for every glyph on the page. Sizing is left to the
   consumer: the toolbar search is 14px. */

function SearchIcon() {
  return (
    <Glyph className="h-3.5 w-3.5">
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
    </Glyph>
  );
}

function StarIcon() {
  return (
    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <Glyph className="h-4 w-4">
      <path d="M6 18L18 6M6 6l12 12" />
    </Glyph>
  );
}

/* Small muted glyphs that lead each field row in the view panel, mirroring the
   record-panel rhythm: icon, label, value. */
const SparkleIcon = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <Glyph className={className}><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" /></Glyph>
);

const PublishIcon = () => (
  <Glyph className="h-4 w-4">
    <polyline points="17 1 21 5 17 9" /><path d="M3 11V9a4 4 0 0 1 4-4h14" /><polyline points="7 23 3 19 7 15" /><path d="M21 13v2a4 4 0 0 1-4 4H3" />
  </Glyph>
);
const PauseIcon = () => (
  <Glyph className="h-4 w-4"><rect x="14" y="4" width="4" height="16" rx="1" /><rect x="6" y="4" width="4" height="16" rx="1" /></Glyph>
);
const PlayIcon = () => (
  <Glyph className="h-4 w-4"><polygon points="5 3 19 12 5 21 5 3" /></Glyph>
);
const ViewIcon = () => (
  <Glyph className="h-4 w-4">
    <path d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </Glyph>
);
const EditIcon = () => (
  <Glyph className="h-4 w-4">
    <path d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 16.604a4.5 4.5 0 01-1.897 1.13L4 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
  </Glyph>
);
const CopyIcon = () => (
  <Glyph className="h-4 w-4"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></Glyph>
);
const ArchiveIcon = () => (
  <Glyph className="h-4 w-4"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /></Glyph>
);
const UnarchiveIcon = () => (
  <Glyph className="h-4 w-4"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M8 8v11a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /><path d="M12 2l-3 3h6l-3-3z" /></Glyph>
);
const TrashIcon = () => (
  <Glyph className="h-4 w-4"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" /></Glyph>
);

/* Cell glyphs read as metadata, so they inherit the cell's own color rather
   than carrying a hue of their own — the status dot is the only thing in a row
   allowed to be colored. */
function BillingIcon({ type }: { type: string }) {
  if (type === "recurring") {
    return (
      <Glyph className="h-3.5 w-3.5">
        <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
      </Glyph>
    );
  }
  if (type === "one_time_pack") {
    return (
      <Glyph className="h-3.5 w-3.5">
        <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" /><path d="M7 7h.01" />
      </Glyph>
    );
  }
  return (
    <Glyph className="h-3.5 w-3.5">
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
    </Glyph>
  );
}

function VisibilityIcon({ type }: { type: string }) {
  if (type === "public") {
    return (
      <Glyph className="h-3.5 w-3.5">
        <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="4" /><line x1="21.17" y1="8" x2="12" y2="8" /><line x1="3.95" y1="6.06" x2="8.54" y2="14" /><line x1="10.88" y1="21.94" x2="15.46" y2="14" />
      </Glyph>
    );
  }
  if (type === "members_only") {
    return (
      <Glyph className="h-3.5 w-3.5">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="19" y1="8" x2="19" y2="14" /><line x1="22" y1="11" x2="16" y2="11" />
      </Glyph>
    );
  }
  return (
    <Glyph className="h-3.5 w-3.5">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </Glyph>
  );
}

export default function PlansPage() {
  const dock = useAssistantDock();
  const chats = useAssistantChats();
  const [plans, setPlans] = useState<PlanOut[] | null>(null);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PlanOut | null>(null);
  const [filter, setFilter] = useState<"active" | "archived" | "promotions">("active");
  const [search, setSearch] = useState("");
  const [billingFilter, setBillingFilter] = useState(NONE);
  const [visibilityFilter, setVisibilityFilter] = useState(NONE);
  const [featuredFilter, setFeaturedFilter] = useState(NONE);
  const [viewing, setViewing] = useState<PlanOut | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string>("gym");

  async function load() {
    setError("");
    try {
      setPlans(await api.get<PlanOut[]>("/plans"));
    } catch (e) {
      setError((e as ApiError).message);
      setPlans([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  // The offer/plan vocabulary and builder are industry-shaped. Fetch the org's
  // venue type so the header + empty states use the right nouns.
  useEffect(() => {
    api
      .get<OrganizationOut>("/organizations/me")
      .then((org) => setIndustry(org.industry ?? "gym"))
      .catch(() => setIndustry("gym"));
  }, []);

  useRealtimeEvent(["plan.changed"], () => void load());

  const ind = getIndustry(industry);
  const isGym = ind.key === "gym";
  const isOffice = ind.key === "office";
  const canBuild = isGym || isOffice; // academy offer builder is still rolling out

  // Tell the assistant panel what this page is about, so its prompt field asks
  // a question this page can actually answer.
  useAssistantHint(
    isOffice
      ? "Ask about your space plans…"
      : isGym
        ? "Ask about your membership plans…"
        : `Ask about your ${ind.label} plans…`,
  );

  async function act(id: string, action: string) {
    setError("");
    try {
      await api.post(`/plans/${id}/${action}`);
      await load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function confirmDelete() {
    if (!deleteId) return;
    setError("");
    try {
      await api.del(`/plans/${deleteId}`);
      setDeleteId(null);
      await load();
    } catch (e) {
      setError((e as ApiError).message);
      setDeleteId(null);
    }
  }

  const deleting = deleteId ? plans?.find((p) => p.id === deleteId) : null;

  const statusFiltered = plans === null ? null : plans.filter(
    (p) => filter === "active" ? p.status !== "archived" : p.status === "archived"
  );

  const filtered = useMemo(() => {
    if (statusFiltered === null) return null;
    const q = search.toLowerCase();
    return statusFiltered.filter((p) =>
      (!q || p.name.toLowerCase().includes(q) || p.billing_type.toLowerCase().includes(q) || p.audience.toLowerCase().includes(q) || p.visibility.toLowerCase().includes(q) || p.status.toLowerCase().includes(q)) &&
      (billingFilter === NONE || p.billing_type === billingFilter) &&
      (visibilityFilter === NONE || p.visibility === visibilityFilter) &&
      (featuredFilter === NONE || (featuredFilter === "featured" ? p.featured : !p.featured))
    );
  }, [statusFiltered, search, billingFilter, visibilityFilter, featuredFilter]);

  const activePlanFilterCount = [billingFilter, visibilityFilter, featuredFilter].filter((v) => v !== NONE).length;
  function clearPlanFilters() {
    setBillingFilter(NONE); setVisibilityFilter(NONE); setFeaturedFilter(NONE);
  }

  const newPlan = () => { setEditing(null); setShowForm(true); };
  const openPlan = (p: PlanOut) => { setViewing(p); };

  // "Ask AI about this plan": hand the plan to the assistant page as a grounded
  // record context and start the chat with a summary request. Resetting the
  // active thread first is what makes ChatPanel create a new conversation from
  // the handed-over prompt instead of dropping it into the thread already open.
  const askAboutPlan = (p: PlanOut) => {
    setViewing(null);
    chats?.setActiveId(null);
    dock?.askAboutRecord(buildPlanSummaryPrompt(p), { kind: "plan", plan: p });
  };

  // Fold a freshly generated summary back into the list so reopening the same
  // plan (or a realtime reload) does not trigger the model again.
  const mergeSummary = useCallback((updated: PlanOut) => {
    setPlans((prev) =>
      prev ? prev.map((p) => (p.id === updated.id ? { ...p, summary: updated.summary } : p)) : prev,
    );
  }, []);

  return (
    <>
      <PageHeader
        title={ind.offerPageTitle}
        subtitle={ind.offerPageSubtitle}
        action={
          canBuild ? (
            <Button onClick={newPlan}>
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
              {ind.offerNewLabel}
            </Button>
          ) : undefined
        }
      />

      {error && <div className="mb-6"><Alert>{error}</Alert></div>}

      {/* Create / edit lives in a right-side Sheet, not a centred modal. The
          form is long and it is about the table behind it; a sheet keeps the
          workspace visible and reads as "adding something to Space Plans"
          rather than "leaving the page". Header and footer stay put, only the
          body scrolls. */}
      <Sheet
        open={showForm}
        onOpenChange={(open) => {
          if (!open) { setShowForm(false); setEditing(null); }
        }}
      >
        <SheetContent>
          <PlanForm
            key={editing?.id ?? "new"}
            plan={editing}
            industryKey={ind.key}
            onCreated={() => { setShowForm(false); setEditing(null); load(); }}
          />
        </SheetContent>
      </Sheet>

      {/* Destructive confirmation stays a centred AlertDialog: deletion is a
          question with two answers, and it should stop you. Being a Radix
          AlertDialog, outside-press and Escape deliberately do nothing. */}
      <AlertDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null); }}
      >
        <AlertDialogContent>
          <div className="flex items-start justify-between gap-4">
            <AlertDialogTitle>Delete plan</AlertDialogTitle>
            <AlertDialogCancel asChild>
              <button
                type="button"
                aria-label="Close"
                className="-mr-1 -mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
              >
                <CloseIcon />
              </button>
            </AlertDialogCancel>
          </div>
          <AlertDialogDescription className="mt-3">
            <span className="block text-[13px] font-medium text-foreground">
              Delete “{deleting?.name}”?
            </span>
            <span className="mt-1 block">
              This action cannot be undone. The plan will be permanently removed.
            </span>
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Cancel</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmDelete}>Delete plan</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Detail view rides in a sheet too, so View, Edit and the row's ⋮ menu
          all open the same surface beside the table instead of a modal that
          hides it. */}
      <Sheet
        open={!!viewing}
        onOpenChange={(open) => { if (!open) setViewing(null); }}
      >
        <SheetContent className="[--sheet-max-w:520px]">
          {viewing && (
            <PlanView
              key={viewing.id}
              plan={viewing}
              onAskAi={() => askAboutPlan(viewing)}
              onEdit={() => { setViewing(null); setEditing(viewing); setShowForm(true); }}
              onUpdated={mergeSummary}
            />
          )}
        </SheetContent>
      </Sheet>

      {/* Toolbar: the view switcher on the left, search on the right. */}
      <ListToolbar
        tabs={[
          {
            value: "active" as const,
            label: "Active",
            count: plans?.filter((p) => p.status !== "archived").length,
          },
          {
            value: "archived" as const,
            label: "Archived",
            count: plans?.filter((p) => p.status === "archived").length,
          },
          ...(isGym ? [{ value: "promotions" as const, label: "Promo codes" }] : []),
        ]}
        value={filter}
        onChange={setFilter}
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Search plans…"
        hideSearch={filter === "promotions"}
        >
        {filter !== "promotions" ? (
          <ListFilterSheet title="Filter plans" description="Narrow plans by billing, visibility, and featured status." activeCount={activePlanFilterCount} resultCount={filtered?.length ?? 0} onClear={clearPlanFilters}>
            <FieldSelect label="Billing type" value={billingFilter} onChange={setBillingFilter}>
              <SelectItem value={NONE}>All billing types</SelectItem>
              {Array.from(new Set((plans ?? []).map((p) => p.billing_type))).sort().map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Visibility" value={visibilityFilter} onChange={setVisibilityFilter}>
              <SelectItem value={NONE}>All visibility</SelectItem>
              {Array.from(new Set((plans ?? []).map((p) => p.visibility))).sort().map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Featured" value={featuredFilter} onChange={setFeaturedFilter}>
              <SelectItem value={NONE}>All plans</SelectItem><SelectItem value="featured">Featured only</SelectItem><SelectItem value="standard">Standard plans</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
        ) : undefined}
      </ListToolbar>

      {filter === "promotions" && isGym ? <PromotionsPanel plans={plans ?? []} /> : (
      <div className="mt-3 overflow-x-auto">
        {filtered === null ? (
          <Spinner label="Loading offers..." />
        ) : filtered.length === 0 ? (
          filter === "active" && plans?.length === 0 ? (
            isGym ? (
              <EmptyState
                title="No plans yet"
                hint={"Create your first plan — members can’t sign up until one is published."}
                icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></svg>}
                action={<Button onClick={newPlan}>+ Create your first plan</Button>}
              />
            ) : isOffice ? (
              <EmptyState
                title="No space plans yet"
                hint="Publish a space plan so companies can sign seat contracts and get billed."
                icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18" /><path d="M9 7h6M9 11h6M9 15h4" /></svg>}
                action={<Button onClick={newPlan}>+ Create your first space plan</Button>}
              />
            ) : (
              <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
                <p className="text-sm font-semibold text-foreground">
                  No {ind.offerKind} offers yet
                </p>
                <p className="mt-1 max-w-xs text-sm text-muted-foreground">
                  The {ind.label} offer builder is rolling out in an upcoming release. Your venue’s offers will appear here.
                </p>
              </div>
            )
          ) : (
            <EmptyState
              title={search ? `No plans matching "${search}"` : activePlanFilterCount ? "No plans match these filters" : `No ${filter} plans`}
              hint={search || activePlanFilterCount ? "Adjust your search or filters and try again." : filter === "archived" ? "Archive a plan to see it here." : undefined}
              icon={<SearchIcon />}
            />
          )
        ) : (
          <table className={`${TABLE} min-w-[720px]`}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={`${TH} ${CELL_FIRST}`}>Name</th>
                <th className={`${TH} ${CELL}`}>Price</th>
                <th className={`${TH} ${CELL}`}>Billing</th>
                <th className={`${TH} ${CELL}`}>Visibility</th>
                <th className={`${TH} ${CELL}`}>Status</th>
                <th className={`${TH} ${CELL_LAST} w-10`} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => openPlan(p)}
                  className={`group ${TR} ${TR_INTERACTIVE}`}
                >
                  <td className={`${TD} ${CELL_FIRST} py-2.5`}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); openPlan(p); }}
                          className="max-w-[280px] cursor-pointer truncate rounded-sm text-left text-[13px] font-medium leading-5 text-foreground focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
                        >
                          {p.name}
                        </button>
                        {p.featured && <span className="shrink-0 text-warning"><StarIcon /></span>}
                      </div>
                      <div className="mt-0.5 truncate text-[11px] leading-4 text-muted-foreground">
                        {titleCase(p.offer_kind ?? "membership")}
                      </div>
                    </div>
                  </td>

                  <td className={`${TD} ${CELL} py-2.5`}>
                    <div className="tabular-nums">
                      <div className="text-[13px] font-medium leading-5 text-foreground">
                        {money(p.price, p.currency)}
                      </div>
                      <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                        {planCadence(p.billing_type, p.cycle_length, p.cycle_unit)}
                      </div>
                    </div>
                  </td>

                  <td className={`${TD} ${CELL} py-2.5`}>
                    <span className="flex items-center gap-1.5 whitespace-nowrap text-[13px] leading-5 text-foreground">
                      <span className="text-muted-foreground"><BillingIcon type={p.billing_type} /></span>
                      {titleCase(p.billing_type)}
                    </span>
                  </td>

                  <td className={`${TD} ${CELL} py-2.5`}>
                    <span className="flex items-center gap-1.5 whitespace-nowrap text-[13px] leading-5 text-muted-foreground">
                      <VisibilityIcon type={p.visibility} />
                      {titleCase(p.visibility)}
                    </span>
                  </td>

                  <td className={`${TD} ${CELL} py-2.5`}>
                    <Badge tone={statusTone(p.status)}>
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                      {planStatusLabel(p.status)}
                    </Badge>
                  </td>

                  <td className={`${TD} ${CELL_LAST} py-2.5 text-right`} onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100">
                      <RowMenu
                        actions={[
                          ...(p.status !== "archived"
                            ? [
                                ...(p.status === "draft"
                                  ? [{ label: "Publish", icon: <PublishIcon />, onSelect: () => act(p.id, "publish") }]
                                  : []),
                                ...(p.status === "published"
                                  ? [{ label: "Pause", icon: <PauseIcon />, onSelect: () => act(p.id, "pause") }]
                                  : []),
                                ...(p.status === "paused"
                                  ? [{ label: "Resume", icon: <PlayIcon />, onSelect: () => act(p.id, "resume") }]
                                  : []),
                              ]
                            : []),
                          { label: "View", icon: <ViewIcon />, onSelect: () => openPlan(p) },
                          { label: "Edit", icon: <EditIcon />, onSelect: () => { setEditing(p); setShowForm(true); } },
                          { label: "Duplicate", icon: <CopyIcon />, onSelect: () => act(p.id, "duplicate") },
                          ...(p.status !== "archived"
                            ? [{ label: "Archive", icon: <ArchiveIcon />, onSelect: () => act(p.id, "archive"), variant: "destructive" as const }]
                            : [{ label: "Unarchive", icon: <UnarchiveIcon />, onSelect: () => act(p.id, "unarchive") }]),
                          { label: "Delete", icon: <TrashIcon />, onSelect: () => setDeleteId(p.id), variant: "destructive" as const },
                        ]}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      )}
    </>
  );
}

/* A labelled Radix Select. The in-house `ui/Select` portals its listbox to
   <body>, which a Radix dialog (the Sheet) makes inert by setting
   `pointer-events: none` on the body — so its options could not be clicked
   inside the sheet. The Radix-based Select composes as a nested layer, so it
   stays interactive and keeps the sheet open. */
function FieldSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <div>
      <span className="mb-1.5 block text-[13px] font-medium text-foreground">{label}</span>
      <RadixSelect value={value} onValueChange={onChange}>
        <SelectTrigger className="h-9 w-full rounded-md border border-foreground/20 bg-card px-3 text-sm text-foreground outline-none transition-colors hover:border-foreground/35 focus:border-brand focus:ring-2 focus:ring-brand/20">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>{children}</SelectContent>
      </RadixSelect>
    </div>
  );
}

function PlanForm({ plan, industryKey = "gym", onCreated }: { plan?: PlanOut | null; industryKey?: string; onCreated: () => void }) {
  const [name, setName] = useState(plan?.name ?? "");
  const [price, setPrice] = useState(plan ? String(plan.price) : "0");
  const [taxMode, setTaxMode] = useState(plan?.tax_mode ?? "inclusive");
  const [taxRate, setTaxRate] = useState(String(Number(((plan?.tax_rate ?? 0) * 100).toFixed(4))));
  const [joiningFee, setJoiningFee] = useState(plan ? String(plan.joining_fee ?? 0) : "0");
  const [billing, setBilling] = useState(plan?.billing_type ?? "recurring");
  const [cycleUnit, setCycleUnit] = useState(plan?.cycle_unit ?? "month");
  const [cycleLength, setCycleLength] = useState(String(plan?.cycle_length ?? 1));
  const [packSize, setPackSize] = useState(String(plan?.pack_size ?? 10));
  const [validityDays, setValidityDays] = useState(plan?.validity_days ? String(plan.validity_days) : "");
  const [audience, setAudience] = useState(plan?.audience ?? "standard");
  const [familyCapacity, setFamilyCapacity] = useState(String(plan?.family_capacity ?? 4));
  const [includedCredits, setIncludedCredits] = useState(plan?.included_credits ? String(plan.included_credits) : "");
  const [offPeak, setOffPeak] = useState(Boolean(plan?.off_peak_start));
  const [offPeakStart, setOffPeakStart] = useState(plan?.off_peak_start ?? "09:00");
  const [offPeakEnd, setOffPeakEnd] = useState(plan?.off_peak_end ?? "16:00");
  const [visibility, setVisibility] = useState(plan?.visibility ?? "public");
  const [desc, setDesc] = useState(plan?.public_description ?? "");
  const [featured, setFeatured] = useState(plan?.featured ?? false);
  // Office space-offer fields (offer_kind = space).
  const isOffice = industryKey === "office";
  const [spaceType, setSpaceType] = useState(isOffice && plan?.spec && "space_type" in plan.spec ? String(plan.spec.space_type) : "fixed_desk");
  const [term, setTerm] = useState(isOffice && plan?.spec && "term" in plan.spec ? String(plan.spec.term) : "monthly");
  const [roomCredits, setRoomCredits] = useState(isOffice && plan?.spec && "room_credits" in plan.spec ? String(plan.spec.room_credits) : "");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const spec = isOffice
        ? {
            space_type: spaceType,
            term,
            billing: "company_invoice",
            ...(roomCredits !== "" && Number(roomCredits) > 0 ? { room_credits: Number(roomCredits) } : {}),
          }
        : undefined;
      const body: Record<string, unknown> = {
        name,
        price: parseFloat(price) || 0,
        joining_fee: isOffice ? 0 : parseFloat(joiningFee) || 0,
        ...(!isOffice ? { tax_mode: taxMode, tax_rate: Number(taxRate) / 100 } : {}),
        billing_type: billing,
        visibility,
        public_description: desc || null,
        featured: featured || undefined,
        ...(isOffice ? { offer_kind: "space", spec } : {}),
        cycle_unit: billing === "recurring" ? cycleUnit : null,
        cycle_length: billing === "recurring" ? Number(cycleLength) : null,
        pack_size: billing === "one_time_pack" ? Number(packSize) : null,
        validity_days: billing === "one_time_pack" && validityDays ? Number(validityDays) : null,
        ...(!isOffice ? {
          audience,
          family_capacity: audience === "family" ? Number(familyCapacity) : null,
          included_credits: billing === "recurring" && includedCredits ? Number(includedCredits) : null,
          off_peak_start: offPeak ? offPeakStart : null,
          off_peak_end: offPeak ? offPeakEnd : null,
        } : {}),
      };
      if (plan) {
        await api.patch(`/plans/${plan.id}`, body);
      } else {
        await api.post("/plans", body);
      }
      onCreated();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  /* `display: contents` lets the <form> own submit while its children stay the
     Sheet's direct flex items — so SheetBody scrolls and SheetFooter's mt-auto
     still pins the actions to the bottom. The fields sit in one calm column;
     only Billing type + Visibility share a row, because that pair is genuinely
     a two-up choice and stacking everything else just made the sheet top-heavy. */
  return (
    <form onSubmit={submit} className="contents">
      <SheetHeader className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <SheetTitle>{plan ? "Edit plan" : "Create plan"}</SheetTitle>
          <SheetDescription>
            {plan ? "Update plan details" : "Saved as a draft — publish it when ready"}
          </SheetDescription>
        </div>
        <SheetClose asChild>
          <button
            type="button"
            aria-label="Close"
            className="-mr-1 -mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
          >
            <CloseIcon />
          </button>
        </SheetClose>
      </SheetHeader>

      <SheetBody className="space-y-5">
        {error && <Alert>{error}</Alert>}

        <Input
          labelVariant="sentence"
          label={isOffice ? "Space plan name" : "Plan name"}
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={isOffice ? "Fixed Desk" : "Monthly Unlimited"}
        />

        <Input
          labelVariant="sentence"
          label={isOffice ? "Price per seat / term" : "Price"}
          type="number"
          min="0"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          hint={isOffice ? "Companies are billed by invoice; the price above is per seat per term." : undefined}
        />
        {!isOffice && <Input
          labelVariant="sentence"
          label="One-time joining fee"
          type="number"
          min="0"
          step="0.01"
          value={joiningFee}
          onChange={(e) => setJoiningFee(e.target.value)}
          hint="Charged only on the member's first successful payment."
        />}

        {!isOffice && <section className="space-y-3 border-y border-border py-4" aria-label="Plan tax settings">
          <FieldSelect label="Tax behavior" value={taxMode} onChange={setTaxMode}>
            <SelectItem value="inclusive">Included in the plan price</SelectItem>
            <SelectItem value="added">Added to the plan price</SelectItem>
          </FieldSelect>
          <Input label="Tax rate (%)" type="number" required min="0" max="100" step="0.0001" value={taxRate} onChange={(event) => setTaxRate(event.target.value)} hint="Enter the rate applicable to this gym. Rates are not selected automatically by country." />
          <p className="text-xs leading-5 text-muted-foreground">Tax is calculated after promotions, including any joining fee. Changes apply to future quotes and renewals; past receipts keep their recorded breakdown.</p>
        </section>}

        {isOffice && (
          <>
            <FieldSelect label="Space type" value={spaceType} onChange={setSpaceType}>
              <SelectItem value="hot_desk">Hot desk</SelectItem>
              <SelectItem value="fixed_desk">Fixed desk</SelectItem>
              <SelectItem value="private_office">Private office</SelectItem>
              <SelectItem value="meeting_room">Meeting room</SelectItem>
              <SelectItem value="day_pass">Day pass</SelectItem>
            </FieldSelect>

            <FieldSelect label="Billing term" value={term} onChange={setTerm}>
              <SelectItem value="monthly">Monthly</SelectItem>
              <SelectItem value="quarterly">Quarterly</SelectItem>
              <SelectItem value="annual">Annual</SelectItem>
            </FieldSelect>

            <Input
              labelVariant="sentence"
              label="Room credits per term"
              type="number"
              min="0"
              value={roomCredits}
              onChange={(e) => setRoomCredits(e.target.value)}
              hint="Optional — meeting-room credits included with each term."
            />
          </>
        )}

        <div className="grid grid-cols-2 gap-4">
          <FieldSelect label="Billing type" value={billing} onChange={setBilling}>
            <SelectItem value="recurring">Recurring</SelectItem>
            <SelectItem value="one_time_pack">One-time pack</SelectItem>
            <SelectItem value="drop_in">Drop-in</SelectItem>
          </FieldSelect>

          <FieldSelect label="Visibility" value={visibility} onChange={setVisibility}>
            <SelectItem value="public">Public</SelectItem>
            <SelectItem value="members_only">Members only</SelectItem>
            <SelectItem value="invite_only">Invite only</SelectItem>
          </FieldSelect>
        </div>

        {billing === "recurring" && (
          <div className="grid grid-cols-2 gap-4">
            <Input labelVariant="sentence" label="Every" type="number" min="1" max="365" required value={cycleLength} onChange={(e) => setCycleLength(e.target.value)} />
            <FieldSelect label="Cycle unit" value={cycleUnit} onChange={setCycleUnit}>
              <SelectItem value="day">Day</SelectItem>
              <SelectItem value="week">Week</SelectItem>
              <SelectItem value="month">Month</SelectItem>
              <SelectItem value="year">Year</SelectItem>
            </FieldSelect>
          </div>
        )}

        {billing === "one_time_pack" && (
          <div className="grid grid-cols-2 gap-4">
            <Input labelVariant="sentence" label="Class credits" type="number" min="1" required value={packSize} onChange={(e) => setPackSize(e.target.value)} />
            <Input labelVariant="sentence" label="Valid for days" type="number" min="1" placeholder="No expiry" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} />
          </div>
        )}

        {!isOffice && (
          <div className="space-y-4 border-t border-foreground/10 pt-5">
            <FieldSelect label="Who is this for?" value={audience} onChange={setAudience}>
              <SelectItem value="standard">Everyone</SelectItem>
              <SelectItem value="student">Students</SelectItem>
              <SelectItem value="family">Family</SelectItem>
            </FieldSelect>
            {audience === "family" && <Input labelVariant="sentence" label="Covered people, including payer" type="number" min="2" max="20" required value={familyCapacity} onChange={(e) => setFamilyCapacity(e.target.value)} />}
            {billing === "recurring" && <Input labelVariant="sentence" label="Visit credits per term" type="number" min="1" placeholder="Unlimited" value={includedCredits} onChange={(e) => setIncludedCredits(e.target.value)} hint="Optional. Shared across all covered family members." />}
            <label className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={offPeak} onChange={(e) => setOffPeak(e.target.checked)} /> Off-peak hours</label>
            {offPeak && <div className="grid grid-cols-2 gap-4">
              <Input labelVariant="sentence" label="From (local time)" type="time" required value={offPeakStart} onChange={(e) => setOffPeakStart(e.target.value)} />
              <Input labelVariant="sentence" label="Until (local time)" type="time" required value={offPeakEnd} onChange={(e) => setOffPeakEnd(e.target.value)} />
            </div>}
          </div>
        )}

        <Textarea
          labelVariant="sentence"
          label="Public description"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder={isOffice ? "What companies see when choosing a plan" : "What members see on the signup screen"}
          rows={4}
        />

        <label className="flex items-center gap-2.5 text-[13px] text-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={featured}
            onChange={(e) => setFeatured(e.target.checked)}
            className="h-4 w-4 rounded border-[var(--border)] bg-[var(--surface)] text-[var(--primary)] accent-[var(--primary)]"
          />
          Featured plan
        </label>
      </SheetBody>

      <SheetFooter>
        <SheetClose asChild>
          <Button type="button" variant="secondary">Cancel</Button>
        </SheetClose>
        <Button type="submit" loading={loading}>{plan ? "Save changes" : "Save draft"}</Button>
      </SheetFooter>
    </form>
  );
}

/* Read-only counterpart to PlanForm: a header with corner actions, the shared
   field rows, and the AI-written plan summary at the foot. */
function PlanView({
  plan,
  onAskAi,
  onEdit,
  onUpdated,
}: {
  plan: PlanOut;
  onAskAi: () => void;
  onEdit: () => void;
  onUpdated: (plan: PlanOut) => void;
}) {
  const [summary, setSummary] = useState(plan.summary ?? "");
  const [loadingSummary, setLoadingSummary] = useState(!plan.summary);
  const [summaryError, setSummaryError] = useState("");

  // Generate on open, then record it on the plan. Later opens read the stored
  // text straight off the list payload, so the model runs at most once. The
  // component is keyed by plan id, so initial state already reflects `plan`.
  useEffect(() => {
    if (plan.summary) return;
    let cancelled = false;
    api
      .post<PlanOut>(`/plans/${plan.id}/summary`)
      .then((updated) => {
        if (cancelled) return;
        setSummary(updated.summary ?? "");
        onUpdated(updated);
      })
      .catch((e) => {
        if (!cancelled) setSummaryError((e as ApiError).message);
      })
      .finally(() => {
        if (!cancelled) setLoadingSummary(false);
      });
    return () => { cancelled = true; };
  }, [plan.id, plan.summary, onUpdated]);

  const statusLabel = planStatusLabel(plan.status);

  return (
    <>
      <SheetHeader className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <SheetTitle className="text-[17px]">{plan.name}</SheetTitle>
          <SheetDescription>
            {titleCase(plan.offer_kind ?? "membership")} offer · {statusLabel}
          </SheetDescription>
          {plan.featured && (
            <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-warning">
              <StarIcon /> Featured
            </span>
          )}
        </div>
        <div className="-mr-1 flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            aria-label="Ask the assistant about this plan"
            title="Ask AI about this plan"
            onClick={onAskAi}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
          >
            <SparkleIcon className="h-4 w-4" />
          </button>
          <SheetClose asChild>
            <button
              type="button"
              aria-label="Close"
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
            >
              <CloseIcon />
            </button>
          </SheetClose>
        </div>
      </SheetHeader>

      <SheetBody className="space-y-6">
        <PlanFields plan={plan} />

        <div className="border-t border-foreground/[0.08] pt-5">
          <div className="mb-2 flex items-center gap-1.5 text-muted-foreground">
            <SparkleIcon />
            <span className="text-[12px] font-medium">Plan summary</span>
          </div>
          {loadingSummary ? (
            <div>
              <div className="space-y-2" aria-hidden>
                <span className="block h-3 w-full animate-pulse rounded bg-foreground/[0.06]" />
                <span className="block h-3 w-[92%] animate-pulse rounded bg-foreground/[0.06]" />
                <span className="block h-3 w-[68%] animate-pulse rounded bg-foreground/[0.06]" />
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">Writing summary…</p>
            </div>
          ) : summaryError ? (
            <p className="text-[13px] text-muted-foreground">{summaryError}</p>
          ) : (
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/90">{summary}</p>
          )}
        </div>
      </SheetBody>

      <SheetFooter>
        <SheetClose asChild>
          <Button type="button" variant="secondary">Close</Button>
        </SheetClose>
        <Button type="button" onClick={onEdit}>Edit plan</Button>
      </SheetFooter>
    </>
  );
}
