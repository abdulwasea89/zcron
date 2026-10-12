// Plan-specific display helpers and the grounded prompt the assistant page
// auto-sends when it is opened from a plan. Kept out of `lib/format.ts` so the
// generic formatters stay domain-agnostic.

import { titleCase } from "@/lib/format";
import type { PlanOut } from "@/lib/types";

/** What a plan's price is *per*, so the number in a price cell is not bare. */
export function planCadence(billingType: string, cycleLength?: number | null, cycleUnit?: string | null): string {
  if (billingType === "recurring") {
    const length = cycleLength ?? 1;
    const unit = cycleUnit ?? "month";
    return `/${length === 1 ? "" : `${length} `}${unit}${length === 1 ? "" : "s"}`;
  }
  if (billingType === "one_time_pack") return "one-time";
  return "per visit";
}

const PLAN_STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  published: "Published",
  paused: "Paused",
  archived: "Archived",
};

export function planStatusLabel(status: string): string {
  return PLAN_STATUS_LABEL[status] ?? titleCase(status);
}

/**
 * The opening question the assistant page sends when opened from a plan.
 *
 * Deliberately short: the plan's fields are already shown in the record panel
 * beside the thread, so the question only needs to name the plan and ask the
 * model to explain it. The name lets the assistant resolve the row through its
 * list-plans tool.
 */
export function buildPlanSummaryPrompt(plan: PlanOut): string {
  return `Summarise the plan "${plan.name}" — what it is and why.`;
}
