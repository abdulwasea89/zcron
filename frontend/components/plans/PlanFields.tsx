import type { ReactNode } from "react";
import { Glyph } from "@/components/Glyph";
import { Badge } from "@/components/ui";
import { money, statusTone, titleCase } from "@/lib/format";
import { planCadence, planStatusLabel } from "@/lib/plans";
import type { PlanOut } from "@/lib/types";

/* Small muted glyphs that lead each field row, mirroring a record-panel
   rhythm: icon, label, value. */
const IdIcon = () => (
  <Glyph className="h-3.5 w-3.5"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M8 9h8M8 13h5" /></Glyph>
);
const LayersIcon = () => (
  <Glyph className="h-3.5 w-3.5"><path d="M12 2l9 5-9 5-9-5 9-5z" /><path d="M3 12l9 5 9-5" /></Glyph>
);
const TagIcon = () => (
  <Glyph className="h-3.5 w-3.5"><path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" /><path d="M7 7h.01" /></Glyph>
);
const RepeatIcon = () => (
  <Glyph className="h-3.5 w-3.5"><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></Glyph>
);
const GlobeIcon = () => (
  <Glyph className="h-3.5 w-3.5"><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z" /></Glyph>
);
const StatusIcon = () => (
  <Glyph className="h-3.5 w-3.5"><circle cx="12" cy="12" r="9" /></Glyph>
);
const TextIcon = () => (
  <Glyph className="h-3.5 w-3.5"><path d="M4 6h16M4 12h16M4 18h10" /></Glyph>
);
const BuildingIcon = () => (
  <Glyph className="h-3.5 w-3.5"><path d="M3 21h18M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" /><path d="M9 8h6M9 12h6M9 16h4" /></Glyph>
);
const CalendarIcon = () => (
  <Glyph className="h-3.5 w-3.5"><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></Glyph>
);
const DoorIcon = () => (
  <Glyph className="h-3.5 w-3.5"><path d="M13 4h3a2 2 0 0 1 2 2v14" /><path d="M2 20h20" /><path d="M5 20V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v14" /><circle cx="11" cy="12" r="1" /></Glyph>
);

function FieldRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground">{icon}</span>
      <span className="w-24 shrink-0 pt-px text-[13px] text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 text-[13px] leading-5 text-foreground">{children}</span>
    </div>
  );
}

/** The read-only record rows for a plan. Shared by the plan sheet and the
 *  assistant's record panel so the two never drift. */
export function PlanFields({ plan }: { plan: PlanOut }) {
  const spec = plan.spec ?? {};
  const isSpace = !!plan.offer_kind && plan.offer_kind !== "membership";
  const statusLabel = planStatusLabel(plan.status);

  return (
    <div className="divide-y divide-foreground/[0.06]">
      <FieldRow icon={<IdIcon />} label="Name">{plan.name}</FieldRow>
      <FieldRow icon={<LayersIcon />} label="Offer">{titleCase(plan.offer_kind ?? "membership")}</FieldRow>
      <FieldRow icon={<TagIcon />} label="Price">
        <span className="font-medium tabular-nums">{money(plan.price, plan.currency)}</span>
        <span className="ml-1.5 text-muted-foreground">{planCadence(plan.billing_type, plan.cycle_length, plan.cycle_unit)}</span>
      </FieldRow>
      <FieldRow icon={<RepeatIcon />} label="Billing">{titleCase(plan.billing_type)}</FieldRow>
      {plan.offer_kind === "membership" && (
        <>
          <FieldRow icon={<LayersIcon />} label="Audience">{titleCase(plan.audience)}</FieldRow>
          {plan.family_capacity && <FieldRow icon={<LayersIcon />} label="Family size">Up to {plan.family_capacity} people</FieldRow>}
          {plan.billing_type === "recurring" && <FieldRow icon={<CalendarIcon />} label="Cycle">Every {plan.cycle_length} {plan.cycle_unit}{plan.cycle_length === 1 ? "" : "s"}</FieldRow>}
          {plan.billing_type === "one_time_pack" && <FieldRow icon={<TagIcon />} label="Class pack">{plan.pack_size} credits{plan.validity_days ? ` · valid ${plan.validity_days} days` : ""}</FieldRow>}
          {plan.included_credits && <FieldRow icon={<TagIcon />} label="Visit credits">{plan.included_credits} per term</FieldRow>}
          {plan.off_peak_start && <FieldRow icon={<CalendarIcon />} label="Off-peak">{plan.off_peak_start}–{plan.off_peak_end} local time</FieldRow>}
        </>
      )}
      <FieldRow icon={<GlobeIcon />} label="Visibility">{titleCase(plan.visibility)}</FieldRow>
      <FieldRow icon={<StatusIcon />} label="Status">
        <Badge tone={statusTone(plan.status)}>
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
          {statusLabel}
        </Badge>
      </FieldRow>

      {isSpace && "space_type" in spec && (
        <FieldRow icon={<BuildingIcon />} label="Space type">{titleCase(String(spec.space_type))}</FieldRow>
      )}
      {isSpace && "term" in spec && (
        <FieldRow icon={<CalendarIcon />} label="Term">{titleCase(String(spec.term))}</FieldRow>
      )}
      {isSpace && "room_credits" in spec && (
        <FieldRow icon={<DoorIcon />} label="Room credits">{String(spec.room_credits)} per term</FieldRow>
      )}
      {plan.public_description && (
        <FieldRow icon={<TextIcon />} label="Description">
          <span className="whitespace-pre-wrap break-words">{plan.public_description}</span>
        </FieldRow>
      )}
    </div>
  );
}
