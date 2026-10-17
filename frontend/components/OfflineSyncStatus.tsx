"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import {
  listOfflineMutations,
  OFFLINE_QUEUE_CHANGE_EVENT,
  removeOfflineMutation,
  updateOfflineMutation,
  type OfflineMutation,
} from "@/lib/offline-mutations";

export function OfflineSyncStatus({ organizationId }: { organizationId: string }) {
  const [online, setOnline] = useState(true);
  const [usingCachedData, setUsingCachedData] = useState(false);
  const [items, setItems] = useState<OfflineMutation[]>([]);
  const [syncing, setSyncing] = useState(false);
  const syncingRef = useRef(false);

  const refresh = useCallback(async () => {
    try { setItems(await listOfflineMutations(organizationId)); } catch { setItems([]); }
  }, [organizationId]);

  const sync = useCallback(async () => {
    if (!navigator.onLine || syncingRef.current) return;
    syncingRef.current = true;
    setSyncing(true);
    try {
      const pending = await listOfflineMutations(organizationId);
      for (const item of pending) {
        try {
          const response = await fetch(`/api/proxy${item.path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Idempotency-Key": item.idempotencyKey },
            body: JSON.stringify(item.body),
          });
          if (response.ok) {
            await removeOfflineMutation(item.id);
            window.dispatchEvent(new CustomEvent("acron:offline-mutation-synced", { detail: { path: item.path } }));
            continue;
          }
          const data = await response.json().catch(() => null) as { detail?: unknown } | null;
          if (response.status >= 400 && response.status < 500) {
            const detail = typeof data?.detail === "string" ? data.detail : `Sync rejected (${response.status}).`;
            await updateOfflineMutation({ ...item, state: "failed", error: detail });
          }
        } catch {
          break; // Network dropped mid-flush; retain this and all later operations.
        }
      }
      await refresh();
    } finally {
      syncingRef.current = false;
      setSyncing(false);
    }
  }, [organizationId, refresh]);

  useEffect(() => {
    const onlineHandler = () => { setOnline(true); void sync(); };
    const offlineHandler = () => setOnline(false);
    const cachedHandler = () => setUsingCachedData(true);
    const freshHandler = () => setUsingCachedData(false);
    const changedHandler = () => { void refresh(); };
    queueMicrotask(() => setOnline(navigator.onLine));
    queueMicrotask(() => { void refresh(); });
    if (navigator.onLine) void sync();
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(async (registration) => {
        const ready = await navigator.serviceWorker.ready;
        (ready.active ?? registration.active)?.postMessage({ type: "SET_WORKSPACE", organizationId });
      }).catch(() => {});
    }
    window.addEventListener("online", onlineHandler);
    window.addEventListener("offline", offlineHandler);
    window.addEventListener("acron:offline-data", cachedHandler);
    window.addEventListener("acron:fresh-data", freshHandler);
    window.addEventListener(OFFLINE_QUEUE_CHANGE_EVENT, changedHandler);
    return () => {
      window.removeEventListener("online", onlineHandler);
      window.removeEventListener("offline", offlineHandler);
      window.removeEventListener("acron:offline-data", cachedHandler);
      window.removeEventListener("acron:fresh-data", freshHandler);
      window.removeEventListener(OFFLINE_QUEUE_CHANGE_EVENT, changedHandler);
    };
  }, [organizationId, refresh, sync]);

  if (online && items.length === 0 && !usingCachedData) return null;
  const failed = items.filter((item) => item.state === "failed").length;
  return (
    <aside aria-live="polite" className="fixed bottom-4 left-4 z-40 flex max-w-[min(92vw,34rem)] flex-wrap items-center gap-3 rounded-lg border border-border bg-surface/95 px-4 py-3 text-sm shadow-xl backdrop-blur">
      <span className={`h-2 w-2 shrink-0 rounded-full ${online ? "bg-warning" : "bg-danger"}`} />
      <span className="min-w-0 flex-1">
        {!online ? `Offline · ${items.length} action${items.length === 1 ? "" : "s"} saved on this device` : usingCachedData && items.length === 0 ? "Connection issue · showing saved workspace data" : failed ? `${failed} saved action${failed === 1 ? " needs" : "s need"} attention` : `${items.length} saved action${items.length === 1 ? "" : "s"} waiting to sync`}
      </span>
      {online && items.some((item) => item.state === "queued") && <Button className="h-8 px-3 text-xs" variant="secondary" loading={syncing} onClick={() => void sync()}>Sync now</Button>}
      {failed > 0 && <details className="basis-full text-xs text-muted-foreground">
        <summary className="cursor-pointer">Review rejected actions</summary>
        <ul className="mt-2 space-y-1">
          {items.filter((item) => item.state === "failed").map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-3">
              <span className="break-words">{item.path}: {item.error || "The server rejected this action."}</span>
              <button type="button" className="shrink-0 text-brand underline" onClick={() => void removeOfflineMutation(item.id)}>Dismiss</button>
            </li>
          ))}
        </ul>
      </details>}
    </aside>
  );
}
