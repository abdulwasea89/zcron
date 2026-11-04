export function dashboardName(fullName: string | null | undefined, email?: string) {
  const name = fullName?.trim().split(/\s+/)[0];
  // A login handle is not a verified given name.
  if (!name || name.includes("@") || /[\d_]/.test(name) || name.toLowerCase() === email?.split("@")[0].toLowerCase()) return null;
  return name.charAt(0).toLocaleUpperCase() + name.slice(1);
}

export function dashboardNumber(value: number, currency?: string, compact = false) {
  return new Intl.NumberFormat("en-US", {
    ...(currency ? { style: "currency" as const, currency } : {}),
    notation: compact && Math.abs(value) >= 10000 ? "compact" : "standard",
    maximumFractionDigits: currency && !compact ? 2 : currency && Math.abs(value) < 10000 ? 2 : 1,
    ...(currency && Math.abs(value) < 10000 ? { minimumFractionDigits: 2 } : {}),
  }).format(value);
}
