"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ListToolbar } from "@/components/ListToolbar";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  EmptyState,
  Spinner,
} from "@/components/ui";
import { useRealtimeEvent } from "@/components/Realtime";
import { QrScanner } from "@/components/attendance/QrScanner";
import { useModuleGate } from "@/hooks/useModuleGate";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { api, ApiError } from "@/lib/api";
import { money, titleCase } from "@/lib/format";
import type {
  AttendanceMember,
  AttendanceOut,
  AttendanceSummary,
  CheckInOut,
} from "@/lib/types";

/* ─── Attendance console (#18) ───
   The front desk's check-in surface. Search (or scan) → check in → the visit is
   logged and its status-on-check-in flags (dues, expired, birthday, slipping)
   surface immediately so the desk can act. Today's feed is live over the
   WebSocket, so a second desk / a member's app shows up here without refresh.

   Offline (#23): the roster is cached, so search works with no network, and
   check-ins are queued locally and flushed to /attendance/sync on reconnect. */

const ROSTER_KEY = "acron.attendance.roster";
const QUEUE_KEY = "acron.attendance.queue";

type QueuedCheckin = {
  id: string;
  member_id: string;
  name: string;
  method: "manual" | "qr";
  checked_in_at: string;   // naive UTC, "YYYY-MM-DDTHH:MM:SS"
  idempotency_key: string;
};

function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "grace" || status === "pending_payment") return "warning";
  if (status === "expired" || status === "banned") return "danger";
  return "neutral";
}

/** Flags shown after a check-in: what the desk should notice about this member. */
type StatusLike = {
  payment_due?: boolean;
  amount_due?: number | null;
  currency?: string | null;
  birthday_today?: boolean;
  at_risk?: boolean;
  days_since_last_visit?: number | null;
};

/** The status-on-check-in badges (#19): dues (with amount), birthday, slipping. */
function StatusBadges({ item }: { item: StatusLike }) {
  return (
    <>
      {item.payment_due && (
        <Badge tone="danger" size="sm">
          {item.amount_due != null
            ? `Due ${money(item.amount_due, item.currency ?? "USD")}`
            : "Dues owed"}
        </Badge>
      )}
      {item.birthday_today && <Badge tone="info" size="sm">Birthday</Badge>}
      {item.at_risk && <Badge tone="warning" size="sm">Slipping</Badge>}
    </>
  );
}

/** Accept `acron:member:<id>` or a bare member id from a scanned code. */
function parseMemberId(text: string): string {
  const trimmed = text.trim();
  const prefix = "acron:member:";
  return trimmed.startsWith(prefix) ? trimmed.slice(prefix.length) : trimmed;
}

function clock(iso: string): string {
  return new Date(iso + "Z").toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function relTime(iso: string, now: number): string {
  const s = Math.max(0, Math.floor((now - new Date(iso + "Z").getTime()) / 1000));
  if (s < 45) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso + "Z").toLocaleDateString();
}

export default function AttendancePage() {
  const { ready } = useModuleGate("attendance");
  const currentUser = useCurrentUser();
  const canManageCards = currentUser?.role === "owner" || currentUser?.role === "manager";

  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [today, setToday] = useState<AttendanceOut[] | null>(null);
  const [results, setResults] = useState<AttendanceMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"today" | "members">("today");
  const [feedSearch, setFeedSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [lastCheckIn, setLastCheckIn] = useState<{ name: string; res: CheckInOut } | null>(null);
  const [scanning, setScanning] = useState(false);
  const [cardUid, setCardUid] = useState("");
  const [cardBusy, setCardBusy] = useState(false);
  const [assigningMember, setAssigningMember] = useState<string | null>(null);
  const [assignUid, setAssignUid] = useState("");
  const cardInputRef = useRef<HTMLInputElement>(null);
  const [now, setNow] = useState(() => Date.now());
  const searchRef = useRef<HTMLInputElement>(null);

  // Offline (#23): cached roster, a local queue, and the current connectivity.
  const [online, setOnline] = useState(true);
  const [roster, setRoster] = useState<AttendanceMember[]>([]);
  const [queue, setQueue] = useState<QueuedCheckin[]>([]);
  const [syncing, setSyncing] = useState(false);

  const loadToday = useCallback(async () => {
    try {
      setToday(await api.get<AttendanceOut[]>("/attendance/today"));
    } catch (e) {
      setError((e as ApiError).message);
      setToday([]);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.get<AttendanceSummary>("/attendance/summary"));
    } catch {
      /* summary is secondary; the console still works without it */
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadToday();
      void loadSummary();
    });
  }, [loadToday, loadSummary]);

  // Cache the roster so offline search still works; load any queued check-ins.
  useEffect(() => {
    queueMicrotask(() => {
      setRoster(loadJSON<AttendanceMember[]>(ROSTER_KEY, []));
      setQueue(loadJSON<QueuedCheckin[]>(QUEUE_KEY, []));
      setOnline(navigator.onLine);
    });
  }, []);

  const refreshRoster = useCallback(async () => {
    try {
      const rows = await api.get<AttendanceMember[]>("/attendance/roster");
      setRoster(rows);
      localStorage.setItem(ROSTER_KEY, JSON.stringify(rows));
    } catch {
      /* keep the cached roster */
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void refreshRoster());
  }, [refreshRoster]);

  const flush = useCallback(
    async (items: QueuedCheckin[]) => {
      if (items.length === 0) return;
      setSyncing(true);
      try {
        const res = await api.post<{ results: { id: string; status: string }[] }>(
          "/attendance/sync",
          {
            items: items.map((q) => ({
              id: q.id,
              member_id: q.member_id,
              method: q.method,
              checked_in_at: q.checked_in_at,
              idempotency_key: q.idempotency_key,
            })),
          },
        );
        const okIds = new Set(res.results.filter((r) => r.status === "synced").map((r) => r.id));
        setQueue((prev) => {
          const remaining = prev.filter((q) => !okIds.has(q.id));
          localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
          return remaining;
        });
        void loadToday();
        void loadSummary();
      } catch {
        setOnline(false); // still offline; retry on the next 'online'
      } finally {
        setSyncing(false);
      }
    },
    [loadToday, loadSummary],
  );

  // Flush leftovers on mount, and whenever connectivity returns.
  useEffect(() => {
    queueMicrotask(() => {
      if (navigator.onLine) {
        const pending = loadJSON<QueuedCheckin[]>(QUEUE_KEY, []);
        if (pending.length) void flush(pending);
      }
    });
  }, [flush]);

  useEffect(() => {
    const up = () => {
      setOnline(true);
      void flush(loadJSON<QueuedCheckin[]>(QUEUE_KEY, []));
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [flush]);

  // Debounced server-side member search (name/email/phone). Gated by
  // TAKE_ATTENDANCE so front desk — the primary user — can read it. The
  // immediate search/clear states are set in the input handler, so the effect
  // only owns the async fetch.
  useEffect(() => {
    const term = query.trim();
    if (term === "" || !online) return;
    let cancelled = false;
    const id = setTimeout(async () => {
      try {
        const rows = await api.get<AttendanceMember[]>(`/attendance/members?q=${encodeURIComponent(term)}`);
        if (!cancelled) setResults(rows);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [query, online]);

  function onQueryChange(value: string) {
    setQuery(value);
    if (value.trim() === "") {
      setResults([]);
      setSearching(false);
    } else {
      setSearching(online);
    }
  }

  // Keep relative timestamps honest.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  // `/` anywhere jumps the cursor into the check-in bar — the front desk lives
  // on the keyboard, so the primary action is always one keystroke away.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
      const el = document.activeElement;
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || (el as HTMLElement | null)?.isContentEditable;
      if (typing) return;
      e.preventDefault();
      setView("members");
      requestAnimationFrame(() => searchRef.current?.focus());
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useRealtimeEvent(["attendance.checked_in"], () => {
    void loadToday();
    void loadSummary();
  });

  const checkIn = useCallback(
    async (memberId: string, name: string, method: "manual" | "qr") => {
      setBusyId(memberId);
      setError("");
      const idem = crypto.randomUUID();

      const enqueue = () => {
        const item: QueuedCheckin = {
          id: crypto.randomUUID(),
          member_id: memberId,
          name,
          method,
          checked_in_at: new Date().toISOString().slice(0, 19),
          idempotency_key: idem,
        };
        setQueue((prev) => {
          const next = [...prev, item];
          localStorage.setItem(QUEUE_KEY, JSON.stringify(next));
          return next;
        });
        setQuery("");
        setResults([]);
        setSearching(false);
        searchRef.current?.focus();
      };

      if (!online) {
        enqueue();
        setBusyId(null);
        return;
      }
      try {
        const res = await api.post<CheckInOut>(
          "/attendance/check-in",
          { member_id: memberId, method },
          { "Idempotency-Key": idem },
        );
        setLastCheckIn({ name: res.member_name || name, res });
        setQuery("");
        setResults([]);
        setSearching(false);
        searchRef.current?.focus();
        void loadToday();
        void loadSummary();
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          // Network failure — drop offline and queue the visit.
          setOnline(false);
          enqueue();
        }
      } finally {
        setBusyId(null);
      }
    },
    [online, loadToday, loadSummary],
  );

  const onCardCheckIn = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const uid = cardUid.trim();
    if (!uid || !online || cardBusy) return;
    setCardBusy(true);
    setError("");
    try {
      const res = await api.post<CheckInOut>("/attendance/card/check-in", { card_uid: uid }, {
        "Idempotency-Key": crypto.randomUUID(),
      });
      setLastCheckIn({ name: res.member_name || "Member", res });
      setCardUid("");
      void loadToday();
      void loadSummary();
      cardInputRef.current?.focus();
    } catch (e) {
      setError((e as ApiError).message || "Could not check in this card.");
    } finally {
      setCardBusy(false);
    }
  }, [cardUid, online, cardBusy, loadToday, loadSummary]);

  const saveCard = useCallback(async (memberId: string) => {
    const uid = assignUid.trim();
    if (!uid) return;
    setBusyId(memberId);
    setError("");
    try {
      await api.put(`/attendance/members/${memberId}/card`, { card_uid: uid });
      setAssigningMember(null);
      setAssignUid("");
      await refreshRoster();
    } catch (e) {
      setError((e as ApiError).message || "Could not link this card.");
    } finally {
      setBusyId(null);
    }
  }, [assignUid, refreshRoster]);

  const removeCard = useCallback(async (memberId: string) => {
    setBusyId(memberId);
    setError("");
    try {
      await api.del(`/attendance/members/${memberId}/card`);
      await refreshRoster();
    } catch (e) {
      setError((e as ApiError).message || "Could not remove this card.");
    } finally {
      setBusyId(null);
    }
  }, [refreshRoster]);

  const onScan = useCallback(
    async (text: string) => {
      setScanning(false);
      const memberId = parseMemberId(text);
      if (/^[0-9a-f]{16,}$/i.test(memberId)) {
        await checkIn(memberId, "", "qr");
      } else {
        setError("That QR code is not a member code for this gym.");
      }
    },
    [checkIn],
  );

  // Offline search runs over the cached roster; online uses the server results.
  const offlineResults = useMemo(() => {
    const t = query.trim().toLowerCase();
    if (!t) return [];
    return roster
      .filter(
        (m) =>
          (m.member_name ?? "").toLowerCase().includes(t) ||
          m.member_email.toLowerCase().includes(t) ||
          (m.phone ?? "").includes(query.trim()),
      )
      .slice(0, 8);
  }, [query, roster]);
  const shown = online ? results : offlineResults;
  const memberRows = query.trim() ? shown : roster;
  const filteredToday = (today ?? []).filter((item) =>
    `${item.member_name ?? ""} ${item.method} ${clock(item.checked_in_at)}`.toLowerCase().includes(feedSearch.toLowerCase()),
  );

  function onSearchKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && shown.length > 0) {
      e.preventDefault();
      const top = shown[0];
      void checkIn(top.member_id, top.member_name || top.member_email, "manual");
    } else if (e.key === "Escape") {
      onQueryChange("");
    }
  }

  if (!ready) return <Spinner label="Loading check-in…" />;

  return (
    <>
      <PageHeader
        title="Check-in"
        subtitle="Track arrivals and check members in."
        action={(
          <div className="flex flex-wrap items-center gap-2">
            <form onSubmit={onCardCheckIn} className="flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1">
              <label htmlFor="attendance-card-uid" className="sr-only">Scan member card</label>
              <input
                id="attendance-card-uid"
                ref={cardInputRef}
                value={cardUid}
                onChange={(event) => setCardUid(event.target.value)}
                placeholder={online ? "Scan card and press Enter" : "Card scan needs internet"}
                disabled={!online || cardBusy}
                autoComplete="off"
                className="h-7 w-48 bg-transparent px-1 text-xs text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
              />
              <Button type="submit" variant="secondary" loading={cardBusy} disabled={!cardUid.trim() || !online}>Check card</Button>
            </form>
            <Button variant="secondary" onClick={() => setScanning(true)}>Scan QR</Button>
          </div>
        )}
      />

      {error && (
        <div className="mb-4">
          <Alert onDismiss={() => setError("")}>{error}</Alert>
        </div>
      )}

      {(!online || queue.length > 0) && (
        <div className="mb-4">
          <Alert tone={online ? "warning" : "info"}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>
                {online
                  ? `${queue.length} check-in${queue.length === 1 ? "" : "s"} waiting to sync.`
                  : `Offline — ${queue.length} check-in${queue.length === 1 ? "" : "s"} queued. Search still works; visits sync when you reconnect.`}
              </span>
              {online && queue.length > 0 && (
                <Button
                  variant="secondary"
                  loading={syncing}
                  onClick={() => flush(loadJSON<QueuedCheckin[]>(QUEUE_KEY, []))}
                >
                  Sync now
                </Button>
              )}
            </div>
          </Alert>
        </div>
      )}

      {lastCheckIn && (
        <div className="mb-5"><CheckInReceipt name={lastCheckIn.name} res={lastCheckIn.res} onDismiss={() => setLastCheckIn(null)} /></div>
      )}

      <ListToolbar
        tabs={[
          { value: "today", label: "Today", count: today?.length ?? summary?.today_count },
          { value: "members", label: "Members", count: roster.length },
        ]}
        value={view}
        onChange={setView}
        search={view === "today" ? feedSearch : query}
        onSearch={view === "today" ? setFeedSearch : onQueryChange}
        searchPlaceholder={view === "today" ? "Search check-ins…" : "Search members…"}
        searchRef={view === "members" ? searchRef : undefined}
        onSearchKeyDown={view === "members" ? onSearchKey : undefined}
      />

      <div className="mt-3 overflow-x-auto">
        {view === "today" ? (
          today === null ? <Spinner label="Loading check-ins…" /> :
          filteredToday.length === 0 ? <EmptyState title={feedSearch ? "No matching check-ins" : "No check-ins yet today"} hint="Visits logged at the desk or in the app appear here." /> :
          <table className={TABLE + " min-w-[720px]"}>
            <thead><tr className={THEAD_ROW}>
              <th className={TH + " " + CELL_FIRST}>Member</th>
              <th className={TH + " " + CELL}>Method</th>
              <th className={TH + " " + CELL}>Time</th>
              <th className={TH + " " + CELL}>Attention</th>
              <th className={TH + " " + CELL_LAST}>Status</th>
            </tr></thead>
            <tbody>{filteredToday.map((a) => <tr key={a.id} className={TR}>
              <td className={TD + " " + CELL_FIRST + " py-3 text-[13px] font-medium"}>{a.member_name || "—"}</td>
              <td className={TD + " " + CELL + " py-3 text-[12px]"}>{titleCase(a.method)}</td>
              <td className={TD + " " + CELL + " py-3 text-[12px]"}>{clock(a.checked_in_at)}<p className="text-[11px] text-muted-foreground">{relTime(a.checked_in_at, now)}</p></td>
              <td className={TD + " " + CELL + " py-3"}><div className="flex flex-wrap gap-1"><StatusBadges item={a} /></div></td>
              <td className={TD + " " + CELL_LAST + " py-3"}><Badge tone="success" size="sm">Checked in</Badge></td>
            </tr>)}</tbody>
          </table>
        ) : (
          searching && memberRows.length === 0 ? <Spinner label="Searching members…" /> :
          memberRows.length === 0 ? <EmptyState title="No matching members" hint="Try another name, email or phone number." /> :
          <table className={TABLE + " min-w-[720px]"}>
            <thead><tr className={THEAD_ROW}>
              <th className={TH + " " + CELL_FIRST}>Member</th>
              <th className={TH + " " + CELL}>Email</th>
              <th className={TH + " " + CELL}>Membership</th>
              <th className={TH + " " + CELL}>Attention</th>
              <th className={TH + " " + CELL_LAST}>Action</th>
            </tr></thead>
            <tbody>{memberRows.map((m) => <tr key={m.member_id} className={TR}>
              <td className={TD + " " + CELL_FIRST + " py-3 text-[13px] font-medium"}>{m.member_name || "—"}</td>
              <td className={TD + " " + CELL + " py-3 text-[12px]"}>{m.member_email}</td>
              <td className={TD + " " + CELL + " py-3"}><Badge tone={statusTone(m.member_status)} size="sm">{titleCase(m.member_status)}</Badge></td>
              <td className={TD + " " + CELL + " py-3"}><div className="flex flex-wrap gap-1"><StatusBadges item={m} /></div></td>
              <td className={TD + " " + CELL_LAST + " py-3"}>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button variant="secondary" disabled={busyId === m.member_id} onClick={() => checkIn(m.member_id, m.member_name || m.member_email, "manual")}>Check in</Button>
                  {canManageCards && (m.has_attendance_card || assigningMember === m.member_id ? (
                    assigningMember === m.member_id ? (
                      <form onSubmit={(event) => { event.preventDefault(); void saveCard(m.member_id); }} className="flex items-center gap-1">
                        <label htmlFor={`assign-card-${m.member_id}`} className="sr-only">Scan card for {m.member_name || m.member_email}</label>
                        <input id={`assign-card-${m.member_id}`} autoFocus value={assignUid} onChange={(event) => setAssignUid(event.target.value)} placeholder="Scan card UID" className="h-8 w-32 rounded border border-border bg-surface px-2 text-xs text-foreground" />
                        <Button type="submit" variant="secondary" disabled={!assignUid.trim() || busyId === m.member_id}>Save</Button>
                        <Button type="button" variant="ghost" onClick={() => { setAssigningMember(null); setAssignUid(""); }}>Cancel</Button>
                      </form>
                    ) : (
                      <>
                        <Button variant="ghost" disabled={!online} onClick={() => { setAssigningMember(m.member_id); setAssignUid(""); }}>Replace card</Button>
                        <Button variant="ghost" disabled={!online || busyId === m.member_id} onClick={() => void removeCard(m.member_id)}>Remove card</Button>
                      </>
                    )
                  ) : (
                    <Button variant="ghost" disabled={!online} onClick={() => { setAssigningMember(m.member_id); setAssignUid(""); }}>Link card</Button>
                  ))}
                </div>
              </td>
            </tr>)}</tbody>
          </table>
        )}
      </div>

      {scanning && <QrScanner onResult={onScan} onClose={() => setScanning(false)} />}
    </>
  );
}

/* The check-in "receipt": who, when, and what the desk should notice. */
function CheckInReceipt({
  name,
  res,
  onDismiss,
}: {
  name: string;
  res: CheckInOut;
  onDismiss: () => void;
}) {
  const who = name || res.member_name || "member";
  const showBadges = res.payment_due || res.birthday_today || res.at_risk;
  return (
    <Card className={`animate-slide-up overflow-hidden ${res.access_warning ? "border-warning-border" : "border-success-border"}`}>
      <div className={`flex items-start gap-3.5 px-5 py-4 ${res.access_warning ? "bg-warning-bg" : "bg-success-bg"}`}>
        <span className="relative shrink-0">
          <Avatar name={who} size="md" />
          <span className={`absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border-2 text-white ${res.access_warning ? "border-[var(--warning-bg)] bg-warning" : "border-[var(--success-bg)] bg-success"}`}>
            {res.access_warning ? "!" : <CheckIcon className="h-3 w-3" />}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold text-foreground">{res.access_warning ? `Visit logged for ${who} — review access` : `Checked in ${who}`}</p>
          {res.hint && (
            <p className="mt-1 text-[12.5px] font-medium text-foreground/90">{res.hint}</p>
          )}
          {res.credit_consumed && <p className="mt-1 text-[12px] text-muted-foreground">1 visit credit used</p>}
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {clock(res.checked_in_at)} · {titleCase(res.method)} ·{" "}
            {res.visits_today === 1 ? "first visit today" : `visit #${res.visits_today} today`}
          </p>
          {showBadges && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <StatusBadges item={res} />
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 cursor-pointer rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </Card>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  );
}
