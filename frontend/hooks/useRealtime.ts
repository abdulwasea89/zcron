"use client";

import { useEffect, useRef, useState } from "react";

export type RtStatus = "connecting" | "live" | "reconnecting" | "offline";
export type RtEvent = { type: string; [k: string]: unknown };

const HEARTBEAT_MS = 25_000;
const MAX_BACKOFF_MS = 15_000;

/** Resolve the WS origin: explicit override, else derive from the backend URL
 * (http→ws), else same-origin. The backend lives on a different port than
 * Next.js in dev, so same-origin alone would target the wrong server. */
function wsBase(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (backend) return backend.replace(/^http/, "ws");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
}

/**
 * Org-scoped realtime connection. Events are signals, not data — the handler
 * should refetch, never render the payload as truth. Auto-reconnects with
 * exponential backoff and heartbeats to survive idle-proxy drops.
 */
export function useRealtime(onEvent: (e: RtEvent) => void): RtStatus {
  const [status, setStatus] = useState<RtStatus>("connecting");
  const handlerRef = useRef(onEvent);
  // Keep the ref current in an effect rather than during render: the socket
  // effect below subscribes once (empty deps) and reads the ref at event time,
  // so the newest handler is used without tearing down the connection.
  useEffect(() => {
    handlerRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let heartbeat: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    const clearTimers = () => {
      if (heartbeat) clearInterval(heartbeat);
      if (retry) clearTimeout(retry);
      heartbeat = retry = null;
    };

    const scheduleReconnect = () => {
      if (disposed) return;
      setStatus("reconnecting");
      const delay = Math.min(1000 * 2 ** attempt++, MAX_BACKOFF_MS);
      retry = setTimeout(connect, delay);
    };

    async function connect() {
      if (disposed) return;
      if (ws?.readyState === WebSocket.OPEN) return;
      setStatus("connecting");
      try {
        const res = await fetch("/api/ws-ticket");
        if (!res.ok) throw new Error("no ticket");
        const { token } = (await res.json()) as { token: string };

        ws = new WebSocket(`${wsBase()}/api/v1/ws`);

        ws.onopen = () => {
          ws?.send(token);
          attempt = 0;
          setStatus("live");
          heartbeat = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), HEARTBEAT_MS);
        };
        ws.onmessage = (m) => {
          const e = JSON.parse(m.data) as RtEvent;
          if (e.type === "pong" || e.type === "connected") return;
          handlerRef.current(e);
        };
        ws.onerror = () => ws?.close();
        ws.onclose = () => {
          clearTimers();
          scheduleReconnect();
        };
      } catch {
        scheduleReconnect();
      }
    }

    const onOnline = () => {
      attempt = 0;
      clearTimers();
      ws?.close();
      connect();
    };
    const onOffline = () => setStatus("offline");

    connect();
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    return () => {
      disposed = true;
      clearTimers();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      ws?.close();
    };
  }, []);

  return status;
}
