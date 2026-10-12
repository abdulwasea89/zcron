"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useSettingsDialog } from "@/components/settings/SettingsProvider";
import type { OrganizationBrief } from "@/lib/types";

/* Icon paths (line icons, 24px viewBox). */
const ICON = {
  gear: "M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z M15 12a3 3 0 11-6 0 3 3 0 016 0z",
  upgrade: "M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941",
  invite: "M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75",
  account: "M18 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM3 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 019.374 21c-2.331 0-4.512-.645-6.374-1.766z",
  plus: "M12 4.5v15m7.5-7.5h-15",
  logout: "M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9",
  check: "M4.5 12.75l6 6 9-13.5",
} as const;

interface OrgSwitcherProps {
  currentOrgName: string;
  currentOrgId?: string;
  /** SaaS tier key (starter | pro | enterprise) for the header subtitle. */
  plan?: string;
  /** Render just the workspace tile (collapsed sidebar rail). */
  compact?: boolean;
}

export function OrgSwitcher({ currentOrgName, currentOrgId, plan, compact }: OrgSwitcherProps) {
  const router = useRouter();
  const settings = useSettingsDialog();
  const [open, setOpen] = useState(false);
  const [orgs, setOrgs] = useState<OrganizationBrief[]>([]);
  const [members, setMembers] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Escape closes the menu.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setLoading(true);
    setError("");
    try {
      setOrgs(await api.get<OrganizationBrief[]>("/auth/my-organizations"));
    } catch {
      setError("Could not load workspaces.");
    } finally {
      setLoading(false);
    }
    // Member count for the header subtitle. Best-effort: some roles can't read
    // analytics, so a failure just omits the count.
    const head = await api
      .get<{ active_members?: number }>("/analytics/headline")
      .catch(() => null);
    setMembers(head?.active_members ?? null);
  }

  async function switchOrg(orgId: string) {
    setOpen(false);
    try {
      const res = await fetch("/api/auth/switch-org", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: orgId }),
      });
      if (!res.ok) throw new Error("Switch failed");
      router.push("/app");
      router.refresh();
    } catch {
      setError("Failed to switch workspace.");
    }
  }

  function go(path: string) {
    setOpen(false);
    router.push(path);
  }

  // Header subtitle, e.g. "Pro Plan · 12 members" — only the parts we know.
  const subtitleParts: string[] = [];
  if (plan) subtitleParts.push(`${titleCase(plan)} Plan`);
  if (members != null) subtitleParts.push(`${members} member${members === 1 ? "" : "s"}`);
  const subtitle = subtitleParts.length ? subtitleParts.join(" · ") : "Workspace";

  async function logout() {
    setOpen(false);
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={toggle}
        title={currentOrgName}
        aria-expanded={open}
        aria-haspopup="menu"
        className={
          compact
            ? "mx-auto flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:bg-foreground/5"
            : "flex h-9 w-full items-center gap-2 rounded-md px-2 text-left transition-colors hover:bg-foreground/5"
        }
      >
        <Tile name={currentOrgName} />
        {!compact && (
          <>
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-foreground">
              {currentOrgName}
            </span>
            <Icon
              d="M19.5 8.25l-7.5 7.5-7.5-7.5"
              className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150 ${open ? "rotate-180" : ""}`}
            />
          </>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-50 mt-1 w-64 animate-fade-in rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1 shadow-lg shadow-black/10"
        >
          {/* Current workspace header. */}
          <div className="flex items-center gap-2.5 rounded-md px-2 py-1.5">
            <Tile name={currentOrgName} />
            <span className="min-w-0 flex-1">
              <span className="block truncate">
                <span
                  className="rounded px-1.5 py-0.5 text-[12px] font-medium text-foreground"
                  style={{ background: `${tileColor(currentOrgName)}14` }}
                >
                  {currentOrgName}
                </span>
              </span>
              <span className="block truncate text-[10px] text-muted-foreground">{subtitle}</span>
            </span>
          </div>

          <Divider />

          <MenuRow icon={ICON.upgrade} label="Upgrade" onClick={() => go("/app/billing")} />
          <MenuRow
            icon={ICON.gear}
            label="Settings"
            onClick={() => {
              setOpen(false);
              settings?.open();
            }}
          />
          <MenuRow icon={ICON.invite} label="Invite members" onClick={() => go("/app/members")} />
          <MenuRow icon={ICON.account} label="Add account" onClick={() => go("/app/account")} />

          <Divider />

          {loading && <p className="px-2 py-2 text-[12px] text-muted-foreground">Loading…</p>}
          {error && <p className="px-2 py-2 text-[12px] text-[var(--danger)]">{error}</p>}
          {!loading && !error && (
            <div className="max-h-64 overflow-y-auto">
              {orgs.map((org) => {
                const isCurrent = org.organization_id === currentOrgId;
                return (
                  <button
                    key={org.organization_id}
                    role="menuitem"
                    onClick={() => switchOrg(org.organization_id)}
                    className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-foreground/5"
                  >
                    <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">
                      <span
                        className="rounded px-1.5 py-0.5"
                        style={{ background: `${tileColor(org.name)}14` }}
                      >
                        {org.name}
                      </span>
                      <span className="text-muted-foreground">
                        {" · "}
                        {org.org_code} · {org.role}
                      </span>
                    </span>
                    {isCurrent && <Icon d={ICON.check} className="h-4 w-4 shrink-0 text-foreground" />}
                  </button>
                );
              })}
            </div>
          )}

          <Divider />

          <MenuRow icon={ICON.plus} label="Create new workspace" onClick={() => go("/app/create-gym")} />
          <MenuRow icon={ICON.logout} label="Log out" onClick={logout} />
        </div>
      )}
    </div>
  );
}

/** A menu action row: icon + label. */
function MenuRow({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/5"
    >
      <Icon d={icon} className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate">{label}</span>
    </button>
  );
}

/** Workspace tile: a rounded square with the workspace initial, colored from a
 *  fixed palette by name so each workspace reads distinctly (and the same one
 *  keeps its color everywhere). */
const TILE_COLORS = [
  "#e03e3e", // red
  "#d9730d", // orange
  "#cb912f", // yellow
  "#448361", // green
  "#2383e2", // blue
  "#9065d0", // purple
  "#c14c8a", // pink
];

function tileColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return TILE_COLORS[hash % TILE_COLORS.length];
}

function Tile({ name }: { name: string }) {
  return (
    <span
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold text-white"
      style={{ background: tileColor(name) }}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

function Divider() {
  return <div className="my-1 h-px bg-[var(--border)]" />;
}

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
