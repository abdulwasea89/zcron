"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useSettingsDialog } from "@/components/settings/SettingsProvider";

/** Settings is a dialog in this workspace, not a navigable route. */
export function WorkspaceAction({ href, children, primary = false, label }: {
  href: string;
  children: ReactNode;
  primary?: boolean;
  label?: string;
}) {
  const settings = useSettingsDialog();
  const className = `workspace-action${primary ? " workspace-action-primary" : ""}`;
  if (href === "/app/settings") {
    return <button type="button" className={className} onClick={() => settings?.open()} aria-label={label}>{children}</button>;
  }
  return <Link href={href} className={className} aria-label={label}>{children}</Link>;
}
