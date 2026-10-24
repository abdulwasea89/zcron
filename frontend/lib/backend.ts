// Server-only client for talking to the FastAPI backend. It injects the auth
// token + org header and transparently refreshes the access token on 401.
import {
  getAccessToken,
  getOrgId,
  getRefreshToken,
  setSession,
} from "./session";

const BASE = process.env.BACKEND_URL ?? "http://localhost:8000";
const PREFIX = "/api/v1";

export class BackendError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

function extractDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0];
      if (typeof first === "string") return first;
      if (typeof first === "object" && first && "msg" in first) {
        return (first as { msg: string }).msg;
      }
    }
  }
  return fallback;
}

interface CallOpts {
  method?: string;
  body?: unknown;
  auth?: boolean; // attach the access token + org header (default true)
  headers?: Record<string, string>;
  retryOn401?: boolean;
}

interface RefreshResult {
  accessToken: string;
  orgId: string | null;
}

async function tryRefresh(): Promise<RefreshResult | null> {
  const refresh = await getRefreshToken();
  if (!refresh) return null;
  const org = await getOrgId();
  const res = await fetch(`${BASE}${PREFIX}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh, organization_id: org ?? null }),
    cache: "no-store",
  });
  if (!res.ok) return null;
  const data = (await res.json()) as {
    access_token: string;
    refresh_token: string;
    organization_id?: string | null;
  };
  try {
    await setSession(data);
  } catch {
    // Non-fatal: cookie will be re-persisted on the next Route Handler hit.
  }
  return { accessToken: data.access_token, orgId: data.organization_id ?? null };
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

async function fetchBackend(path: string, opts: CallOpts): Promise<Response> {
  const { method = "GET", body, auth = true, headers = {}, retryOn401 = true } = opts;

  const h: Record<string, string> = { ...headers };
  const isFormData = body instanceof FormData;
  if (body !== undefined && !isFormData) h["Content-Type"] = "application/json";

  let accessToken: string | undefined;
  let orgId: string | undefined;

  if (auth) {
    accessToken = await getAccessToken();
    if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
    orgId = await getOrgId();
    if (orgId) h["X-Organization-Id"] = orgId;
  }

  const res = await fetch(`${BASE}${PREFIX}${path}`, {
    method,
    headers: h,
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    cache: "no-store",
  });

  // Transparent refresh: on a 401 with a refresh token, refresh once and retry.
  if (res.status === 401 && auth && retryOn401) {
    const refreshResult = await tryRefresh();
    if (refreshResult) {
      const retryH: Record<string, string> = { ...headers };
      if (body !== undefined && !isFormData) retryH["Content-Type"] = "application/json";
      retryH["Authorization"] = `Bearer ${refreshResult.accessToken}`;
      if (refreshResult.orgId) retryH["X-Organization-Id"] = refreshResult.orgId;

      const retryRes = await fetch(`${BASE}${PREFIX}${path}`, {
        method,
        headers: retryH,
        body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
        cache: "no-store",
      });
      return retryRes;
    }
  }

  return res;
}

/** Low-level call to the backend. Returns parsed JSON or throws BackendError. */
export async function backend<T = unknown>(path: string, opts: CallOpts = {}): Promise<T> {
  const res = await fetchBackend(path, opts);
  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    throw new BackendError(res.status, extractDetail(data, `Request failed (${res.status})`));
  }
  return data as T;
}

/** Low-level call returning raw Response (for binary downloads). */
export async function backendRaw(path: string, opts: CallOpts = {}): Promise<Response> {
  const res = await fetchBackend(path, opts);

  if (!res.ok) {
    const text = await res.text();
    const data = text ? safeJson(text) : null;
    throw new BackendError(res.status, extractDetail(data, `Request failed (${res.status})`));
  }
  return res;
}
