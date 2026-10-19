// Client-side API helper. The browser never talks to FastAPI directly — it
// calls same-origin Next.js route handlers under /api/proxy/*, which attach the
// httpOnly auth cookie server-side. This keeps tokens out of JS entirely.
"use client";

import { toast } from "sonner";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const h: Record<string, string> = { ...headers };
  if (body !== undefined) h["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api/proxy${path}`, {
      method,
      headers: Object.keys(h).length > 0 ? h : undefined,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    const message = "Acron could not reach the server. Check your connection and try again.";
    toast.error(message, { id: "acron-network-error" });
    throw new ApiError(0, message);
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(res.headers.get("X-Acron-Offline") === "1" ? "acron:offline-data" : "acron:fresh-data"));
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const raw = data && typeof data === "object" && "detail" in data
      ? (data as { detail: unknown }).detail
      : null;
    const detail = Array.isArray(raw)
      ? raw.map((item) => {
          if (!item || typeof item !== "object") return String(item);
          const issue = item as { loc?: unknown[]; msg?: unknown };
          const field = issue.loc?.filter((part) => part !== "body").join(" → ");
          return [field, issue.msg].filter(Boolean).join(": ");
        }).filter(Boolean).join("; ") || `Request failed (${res.status})`
      : typeof raw === "string" ? raw : `Request failed (${res.status})`;
    if (res.status >= 500) {
      toast.error(detail.slice(0, 220), { id: `acron-api-${res.status}-${detail}` });
    }
    throw new ApiError(res.status, detail);
  }
  if (method !== "GET" && res.status === 201) {
    toast.success("Created successfully.");
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, body, headers),
  patch: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("PATCH", path, body, headers),
  put: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("PUT", path, body, headers),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/** One decoded Server-Sent Events frame. */
function parseFrame(raw: string): unknown {
  const data = raw
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");
  if (!data) return undefined;
  try {
    return JSON.parse(data);
  } catch {
    return undefined;
  }
}

/**
 * POST and consume a Server-Sent Events response, yielding each frame's JSON.
 *
 * Unlike `api.post`, the URL is used as-is: streaming replies have their own
 * route handler (`/api/assistant/stream`), because the generic /api/proxy
 * buffers the body. Frames split on a blank line; a partial frame stays in the
 * buffer until the rest of it lands, so a token straddling two network chunks
 * is never lost or double-counted.
 *
 * Errors surface from the first `next()` as an `ApiError`, so a caller can
 * `throw`-handle it around the `for await`.
 */
export async function* streamPost<T>(
  url: string,
  body?: unknown,
  headers?: Record<string, string>,
  signal?: AbortSignal,
): AsyncGenerator<T> {
  const h: Record<string, string> = { ...headers };
  if (body !== undefined) h["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: h,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch {
    const message = "Acron could not reach the server. Check your connection and try again.";
    toast.error(message, { id: "acron-network-error" });
    throw new ApiError(0, message);
  }

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    let detail = `Request failed (${res.status})`;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed?.detail === "string") detail = parsed.detail;
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    if (res.status >= 500) {
      toast.error(detail.slice(0, 220), { id: `acron-stream-${res.status}-${detail}` });
    }
    throw new ApiError(res.status, detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        const payload = parseFrame(buffer.slice(0, split));
        buffer = buffer.slice(split + 2);
        if (payload !== undefined) yield payload as T;
        split = buffer.indexOf("\n\n");
      }
    }
  } finally {
    // Reached on a normal end and on a caller that breaks out early. In the
    // second case this tears down the connection, which is what stops the
    // backend from generating tokens nobody will read.
    void reader.cancel().catch(() => {});
  }
}
