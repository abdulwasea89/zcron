// Small formatting + status-mapping helpers shared across pages.

export function money(amount: number, currency = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function roleLabel(role: string): string {
  return titleCase(role);
}

export function dateKeyInTimeZone(value: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export type Tone = "neutral" | "success" | "danger" | "warning";

const GYM_STATUS_LABELS: Record<string, string> = {
  open: "Open",
  closed: "Closed",
  half_day: "Half day",
};

export function gymStatusLabel(status: string): string {
  return GYM_STATUS_LABELS[status] ?? titleCase(status);
}

export function gymStatusTone(status: string): Tone {
  if (status === "open") return "success";
  if (status === "closed") return "danger";
  return "warning"; // half_day
}

export function statusTone(status: string): Tone {
  const s = status.toLowerCase();
  if (["active", "succeeded", "published", "paid"].includes(s)) return "success";
  if (["banned", "cancelled", "suspended", "failed", "expired", "read_only"].includes(s)) return "danger";
  if (["grace", "frozen", "past_due", "pending_payment", "pending_approval", "pending_activation", "paused", "draft"].includes(s))
    return "warning";
  return "neutral";
}

/** Tone for a B2B invoice status ("overdue" is derived by the backend). */
export function invoiceTone(status: string): Tone {
  const s = status.toLowerCase();
  if (s === "paid") return "success";
  if (s === "overdue") return "danger";
  if (s === "draft" || s === "partial") return "warning";
  if (s === "sent") return "neutral";
  return "neutral"; // void
}

/** Display label for an invoice status. */
export function invoiceLabel(status: string): string {
  const s = status.toLowerCase();
  if (s === "paid") return "Paid";
  if (s === "overdue") return "Overdue";
  if (s === "partial") return "Part paid";
  if (s === "sent") return "Sent";
  if (s === "draft") return "Draft";
  if (s === "void") return "Void";
  return titleCase(s);
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const DATETIME_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATETIME_FMT.format(d);
}
