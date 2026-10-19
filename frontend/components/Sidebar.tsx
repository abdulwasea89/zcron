"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { OrgSwitcher } from "./OrgSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { SidebarChats } from "./assistant/SidebarChats";
import { useAssistantChats } from "@/components/assistant/AssistantChats";
import { useSettingsDialog } from "@/components/settings/SettingsProvider";
import {
  NAV_LABEL_OVERRIDES,
  NAV_MODULE_BY_HREF,
  getIndustry,
} from "@/lib/industries";

function cx(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(" ");
}

type NavItem = { href: string; label: string; icon: string };

// The gym-reference navigation, in order. Each route is gated by the registry
// module it belongs to; venue verticals filter this list and swap labels.
const NAV: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1" },
  { href: "/app/assistant", label: "Assistant", icon: "M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" },
  { href: "/app/analytics", label: "Analytics", icon: "M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" },
  { href: "/app/plans", label: "Plans", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" },
  { href: "/app/leads", label: "Leads", icon: "M12 6.75a3 3 0 1 1 0 6 3 3 0 0 1 0-6ZM4.5 20.25a7.5 7.5 0 0 1 15 0" },
  { href: "/app/referrals", label: "Referrals", icon: "M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.5 20.25a7.5 7.5 0 0 1 15 0M18 8.25l2.25 2.25m0 0L18 12.75m2.25-2.25h-3" },
  // Office vertical routes. Gated by the registry modules companies/invoices/
  // space, which gym + academy don't enable — so they never appear for them.
  { href: "/app/companies", label: "Companies", icon: "M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" },
  { href: "/app/invoices", label: "Invoices", icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" },
  { href: "/app/space", label: "Space", icon: "M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" },
  { href: "/app/inbox", label: "Inbox", icon: "M2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" },
  { href: "/app/front-desk", label: "Walk-ins", icon: "M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l3 3m0 0l-3 3m3-3H2.25" },
  { href: "/app/members", label: "Members", icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" },
  { href: "/app/onboarding", label: "Onboarding", icon: "M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" },
  { href: "/app/retention", label: "Member retention", icon: "M3 3v18h18M8 14l4-4 4 4 5-7" },
  { href: "/app/payments", label: "Payments", icon: "M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" },
  { href: "/app/cash", label: "Cash", icon: "M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
  { href: "/app/receipts", label: "Receipts", icon: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" },
  { href: "/app/tasks", label: "Tasks", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 12l2 2 4-4" },
  { href: "/app/classes", label: "Classes", icon: "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zm6.75-4.5h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008V15zm0 2.25h.008v.008h-.008v-.008zm2.25-4.5h.008v.008H16.5v-.008zm0 2.25h.008v.008H16.5V15z" },
  { href: "/app/attendance", label: "Check-in", icon: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
  { href: "/app/staff", label: "Staff", icon: "M12 4.5a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5ZM6.75 20.25v-1.5a3.75 3.75 0 0 1 3.75-3.75h3a3.75 3.75 0 0 1 3.75 3.75v1.5" },
  { href: "/app/approvals", label: "Approvals", icon: "M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" },
  { href: "/app/payroll", label: "Payroll", icon: "M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0" },
  { href: "/app/settings", label: "Settings", icon: "M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
];

/** Registry-driven nav for an org's industry. gym (the reference) is returned
 *  byte-for-byte unchanged; office/academy drop routes whose module is off and
 *  relabel venue-specific pages. */
function navFor(industry?: string): NavItem[] {
  const meta = getIndustry(industry);
  const overrides = NAV_LABEL_OVERRIDES[meta.key] ?? {};
  // Secondary administration pages live in Settings > Workspace tools.
  const settingsTools = new Set(["/app/staff", "/app/payroll", "/app/receipts"]);
  return NAV.filter((item) => meta.modules.includes(NAV_MODULE_BY_HREF[item.href]) && !settingsTools.has(item.href)).map(
    (item) => ({ ...item, label: overrides[item.href] ?? item.label }),
  );
}

// Sidebar sections (Notion-style grouping). Kept as a lookup so the NAV list
// above stays the single ordered source of routes. "Overview" renders in the
// top quick-icon row; the rest render as labelled sections below it.
type NavGroup = "Overview" | "Operations" | "Money" | "Organization";
const QUICK_GROUP: NavGroup = "Overview";
const NAV_GROUP_ORDER: NavGroup[] = ["Operations", "Money", "Organization"];
const NAV_GROUP_BY_HREF: Record<string, NavGroup> = {
  "/app": "Overview",
  "/app/assistant": "Overview",
  "/app/analytics": "Overview",
  "/app/members": "Operations",
  "/app/onboarding": "Operations",
  "/app/retention": "Operations",
  "/app/leads": "Operations",
  "/app/referrals": "Operations",
  "/app/plans": "Operations",
  "/app/classes": "Operations",
  "/app/attendance": "Operations",
  "/app/inbox": "Operations",
  "/app/front-desk": "Operations",
  "/app/space": "Operations",
  "/app/tasks": "Operations",
  "/app/approvals": "Operations",
  "/app/payments": "Money",
  "/app/cash": "Money",
  "/app/receipts": "Money",
  "/app/payroll": "Money",
  "/app/invoices": "Money",
  "/app/staff": "Organization",
  "/app/companies": "Organization",
  "/app/settings": "Organization",
};

interface SidebarProps {
  orgName: string;
  orgCode: string;
  orgId?: string;
  /** Venue vertical (gym | office | academy). Drives which nav modules show. */
  industry?: string;
  /** SaaS tier key (starter | pro | enterprise), shown in the workspace menu. */
  tier?: string;
}

/** Shared sign-out handler for the desktop sidebar strip and the mobile header. */
function useLogout() {
  const router = useRouter();
  return useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }, [router]);
}

export function Sidebar({ orgName, orgCode, orgId, industry, tier }: SidebarProps) {
  const pathname = usePathname();
  const items = useMemo(() => navFor(industry), [industry]);
  const logout = useLogout();
  const settings = useSettingsDialog();
  const chats = useAssistantChats();
  const [collapsed, setCollapsed] = useState(false);

  const quickItems = useMemo(
    () => items.filter((item) => NAV_GROUP_BY_HREF[item.href] === QUICK_GROUP),
    [items],
  );
  const isActive = (item: NavItem) =>
    item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);

  // ── Sliding selection pill (Overview tabs) ──────────────────────────────
  // One shared indicator instead of each link painting its own active
  // background: the highlight *glides* between tabs the way native tab bars
  // do, rather than popping into place. Geometry is measured right after
  // commit (the active label mounts synchronously, so the rect is already
  // final); the pill's CSS transition does the travel on a critically damped
  // curve — damping 1.0, response ~0.4s — no overshoot, long soft settle.
  const quickRowRef = useRef<HTMLDivElement | null>(null);
  const pillRef = useRef<HTMLSpanElement | null>(null);
  const quickLinkRefs = useRef(new Map<string, HTMLAnchorElement>());
  const pillPlaced = useRef(false);

  const placePill = useCallback(() => {
    const row = quickRowRef.current;
    const pill = pillRef.current;
    if (!row || !pill) return;
    const active = quickItems.find((item) =>
      item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href),
    );
    const target = active ? quickLinkRefs.current.get(active.href) : undefined;
    if (!target) {
      // Nothing in this group is active (e.g. /app/members) — fade the pill
      // out in place; its last position is where it should reappear from.
      pill.style.opacity = "0";
      return;
    }
    const rowBox = row.getBoundingClientRect();
    const box = target.getBoundingClientRect();
    // First placement snaps (no slide-in from 0,0); everything after it
    // animates. Same easing as the view-transition group in globals.css so
    // the glide is identical whether or not a view transition runs.
    const ease = "cubic-bezier(0.22, 1, 0.36, 1)";
    pill.style.transition = pillPlaced.current
      ? `transform 420ms ${ease}, width 420ms ${ease}, height 420ms ${ease}, opacity 160ms ease-out`
      : "none";
    pill.style.opacity = "1";
    pill.style.transform = `translate3d(${box.left - rowBox.left}px, ${box.top - rowBox.top}px, 0)`;
    pill.style.width = `${box.width}px`;
    pill.style.height = `${box.height}px`;
    pillPlaced.current = true;
  }, [pathname, quickItems]);

  useLayoutEffect(() => {
    placePill();
  }, [placePill]);

  // The row also moves while the sidebar collapses/expands (its width is
  // transitioned over 150ms), so keep re-measuring as it resizes — the pill
  // follows continuously instead of jumping to a stale target.
  useEffect(() => {
    const row = quickRowRef.current;
    if (!row) return;
    const observer = new ResizeObserver(() => placePill());
    observer.observe(row);
    return () => observer.disconnect();
  }, [placePill]);

  return (
    <>
      <MobileNavigation orgName={orgName} orgCode={orgCode} items={items} />
      <aside
        className={cx(
          // `lg:z-30` is load-bearing, not decoration. `sticky` makes this a
          // stacking context, so the workspace menu's z-50 is trapped inside
          // it and can't outrank the page. Without a z-index here the aside
          // sits in the same z-auto band as the content column, which comes
          // LATER in the DOM and therefore paints over it — cards would cover
          // the open menu. Sits under the assistant bar (z-40) and the
          // settings modal (z-[70]); page popovers (z-50) still win.
          "hidden lg:sticky lg:top-0 lg:z-30 lg:flex lg:h-screen lg:shrink-0 lg:flex-col border-r border-foreground/10 bg-surface transition-[width] duration-150",
          collapsed ? "lg:w-[52px]" : "lg:w-64",
        )}
      >
        {/* Expanded: one header row — workspace switcher + collapse. Collapsed:
            the 52px rail has no room for both side by side, so the header is
            the expand button alone and the workspace tile drops to its own row
            below (which also keeps it centred over the nav icons). */}
        <div
          className={cx(
            "flex h-11 shrink-0 items-center px-2",
            collapsed ? "justify-center" : "gap-2",
          )}
        >
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <OrgSwitcher
                currentOrgName={orgName}
                currentOrgId={orgId}
                plan={tier}
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
          >
            <svg className={cx("h-4 w-4 transition-transform", collapsed && "rotate-180")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18.75 19.5l-7.5-7.5 7.5-7.5M12.75 19.5l-7.5-7.5 7.5-7.5" />
            </svg>
          </button>
        </div>

        {/* Collapsed rail: the workspace tile on its own row. */}
        {collapsed && (
          <div className="px-2 pb-1">
            <OrgSwitcher
              currentOrgName={orgName}
              currentOrgId={orgId}
              plan={tier}
              compact
            />
          </div>
        )}

        {/* Quick-icon row (Overview). The pill is the shared selection
            highlight sitting behind the links: links are `relative` so their
            labels/icons paint above it, and `pointer-events-none` keeps hover
            hits on the links. `viewTransitionName` lets it glide as its own
            group during a tab view transition (same curve in globals.css). */}
        <div
          ref={quickRowRef}
          className={cx("relative flex items-center gap-0.5 px-2 pt-1", collapsed && "flex-col")}
        >
          <span
            ref={pillRef}
            aria-hidden="true"
            style={{ viewTransitionName: "sidebar-tab" }}
            className="pointer-events-none absolute left-0 top-0 rounded-md bg-foreground/[0.06] opacity-0"
          />
          {quickItems.map((item) => {
            const active = isActive(item);
            return (
              <Link
                key={item.href}
                ref={(el) => {
                  if (el) quickLinkRefs.current.set(item.href, el);
                  else quickLinkRefs.current.delete(item.href);
                }}
                href={item.href}
                title={item.label}
                aria-current={active ? "page" : undefined}
                // Tags the navigation so only these tabs trigger the
                // content crossfade in the app layout.
                transitionTypes={["tab"]}
                className={cx(
                  "relative flex h-8 items-center rounded-md text-sm transition-colors",
                  active
                    ? cx("gap-2 font-medium text-foreground", collapsed ? "w-8 justify-center px-0" : "px-2.5")
                    : "w-8 justify-center text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
                )}
              >
                <Icon d={item.icon} className={cx("h-[18px] w-[18px] shrink-0", active && "text-foreground/80")} />
                {active && !collapsed && <span className="animate-fade-in">{item.label}</span>}
              </Link>
            );
          })}
        </div>

        {/* Labelled sections */}
        <nav className={cx("mt-3 flex-1 overflow-y-auto pb-2", collapsed ? "px-2" : "px-2")}>
          {NAV_GROUP_ORDER.map((group) => {
            const groupItems = items.filter((item) => NAV_GROUP_BY_HREF[item.href] === group);
            if (groupItems.length === 0) return null;
            return (
              <div key={group} className="mb-3">
                {!collapsed && (
                  <p className="px-2.5 pb-1 text-[10px] font-semibold text-muted-foreground/80">
                    {group}
                  </p>
                )}
                <div className="space-y-0.5">
                  {groupItems.map((item) => {
                    const active = isActive(item);
                    const rowClass = cx(
                      "flex h-8 items-center rounded-md text-sm transition-colors",
                      collapsed ? "justify-center px-0" : "gap-2.5 px-2.5",
                      active
                        ? "bg-foreground/[0.06] font-medium text-foreground"
                        : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
                    );
                    const inner = (
                      <>
                        <Icon
                          d={item.icon}
                          className={cx("h-4 w-4 shrink-0", active ? "text-foreground/80" : "text-foreground/50")}
                        />
                        {!collapsed && item.label}
                      </>
                    );
                    // Settings opens the modal, not a route (Notion-style).
                    if (item.href === "/app/settings") {
                      return (
                        <button
                          key={item.href}
                          type="button"
                          title={item.label}
                          onClick={() => settings?.open()}
                          className={cx(rowClass, "w-full text-left")}
                        >
                          {inner}
                        </button>
                      );
                    }
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        title={item.label}
                        aria-current={active ? "page" : undefined}
                        className={rowClass}
                      >
                        {inner}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Chats sit in the scrolling column with the nav sections, not down
              in the fixed footer: it is a list of variable length, so it has to
              scroll with the rest rather than hold space it may not need. */}
          <SidebarChats collapsed={collapsed} />
        </nav>

        {/* New chat + account */}
        <div className="shrink-0 p-2">
          <div className={cx("flex items-center gap-1.5", collapsed && "flex-col")}>
            <Link
              href="/app/assistant"
              title="New chat"
              // Dropping the open thread is what makes this a *new* chat when
              // you are already on the assistant page; the push alone is to the
              // route you are on, so it would otherwise reopen the same one.
              onClick={() => chats?.setActiveId(null)}
              className={cx(
                "flex h-9 items-center rounded-full border border-foreground/15 bg-secondary text-sm text-foreground/70 transition-colors hover:bg-foreground/10 hover:text-foreground",
                collapsed ? "w-9 justify-center" : "flex-1 gap-2 px-3",
              )}
            >
              <Icon
                d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
                className="h-[18px] w-[18px] shrink-0"
              />
              {!collapsed && "New chat"}
            </Link>
            {!collapsed && (
              <Link
                href="/app/assistant"
                aria-label="New chat"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-foreground/15 bg-secondary text-foreground/70 transition-colors hover:bg-foreground/10 hover:text-foreground"
              >
                <Icon
                  d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zM16.862 4.487L19.5 7.125"
                  className="h-[18px] w-[18px] shrink-0"
                />
              </Link>
            )}
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className={cx(
              "mt-0.5 flex items-center rounded-md text-[12px] text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground",
              collapsed ? "h-9 w-full justify-center px-0" : "w-full gap-2.5 px-2.5 py-2",
            )}
          >
            <Icon
              d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"
              className="h-4 w-4 shrink-0"
            />
            {!collapsed && "Sign out"}
          </button>
        </div>
      </aside>
    </>
  );
}

/** Shared inline line icon. */
function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

function MobileNavigation({
  orgName,
  orgCode,
  items,
}: {
  orgName: string;
  orgCode: string;
  items: NavItem[];
}) {
  const pathname = usePathname();
  const activeRef = useRef<HTMLAnchorElement | null>(null);
  const logout = useLogout();
  const settings = useSettingsDialog();

  // Keep the current page's chip centered in the strip after navigation,
  // the way native top tab bars behave.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [pathname]);

  return (
    <header className="sticky top-0 z-20 border-b border-foreground/10 bg-background/80 backdrop-blur lg:hidden">
      <div className="flex h-14 items-center gap-3 px-4">
        <Link href="/app" className="flex shrink-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-brand" aria-hidden="true" />
          <span className="font-display text-lg leading-none tracking-tight text-foreground">Acron</span>
        </Link>
        <p className="min-w-0 flex-1 truncate text-right font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {orgName} · {orgCode}
        </p>
        <ThemeToggle />
        <button
          type="button"
          onClick={logout}
          className="shrink-0 cursor-pointer list-none font-mono text-[10px] uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-accent)]/50 rounded px-1 py-0.5"
        >
          Sign out
        </button>
      </div>

      {/* Horizontally-scrollable page chips — active state is a solid brand pill (§10.3) */}
      <nav
        aria-label="Mobile navigation"
        className="no-scrollbar flex items-center gap-1.5 overflow-x-auto px-4 pb-2.5"
      >
        {items.map((item) => {
          const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
          const chipClass = cx(
            "flex h-8 shrink-0 items-center whitespace-nowrap rounded-full px-3.5 text-[12px] transition-colors duration-150",
            active
              ? "bg-brand font-medium text-brand-foreground"
              : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
          );
          if (item.href === "/app/settings") {
            return (
              <button
                key={item.href}
                type="button"
                onClick={() => settings?.open()}
                className={chipClass}
              >
                {item.label}
              </button>
            );
          }
          return (
            <Link
              key={item.href}
              href={item.href}
              ref={active ? activeRef : undefined}
              aria-current={active ? "page" : undefined}
              transitionTypes={
                NAV_GROUP_BY_HREF[item.href] === QUICK_GROUP ? ["tab"] : undefined
              }
              className={chipClass}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
