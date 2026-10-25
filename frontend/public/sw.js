/* Acron web offline cache. Private responses are keyed by workspace and are
   removed on sign-out. Only same-origin app documents, Next static assets and
   authenticated read-only API GETs are cached. Mutations are handled by the
   IndexedDB outbox, never by this cache. */
const STATIC_CACHE = "acron-static-v1";
const META_CACHE = "acron-offline-meta-v1";
const META_URL = new URL("/__acron_offline_meta__/active-workspace", self.location.origin).href;
let activeOrganizationId = null;

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const message = event.data || {};
  if (message.type === "SET_WORKSPACE" && typeof message.organizationId === "string") {
    activeOrganizationId = message.organizationId;
    event.waitUntil(caches.open(META_CACHE).then((cache) => cache.put(META_URL, new Response(activeOrganizationId))));
  }
  if (message.type === "CLEAR_PRIVATE_CACHE") {
    activeOrganizationId = null;
    event.waitUntil(Promise.all([
      caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("acron-private-"))
        .map((key) => caches.delete(key)))),
      caches.open(META_CACHE).then((cache) => cache.delete(META_URL)),
    ]));
  }
});

async function currentOrganizationId() {
  if (activeOrganizationId) return activeOrganizationId;
  const metadata = await caches.open(META_CACHE);
  const response = await metadata.match(META_URL);
  activeOrganizationId = response ? await response.text() : null;
  return activeOrganizationId;
}

function scopedKey(request, organizationId) {
  const url = new URL(request.url);
  url.searchParams.set("__acron_offline_org", organizationId);
  if (request.headers.get("RSC") === "1") url.searchParams.set("__acron_rsc", "1");
  return new Request(url.href, { method: "GET" });
}

async function cachedNetworkFirst(request, cacheName, key, isUseful) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (isUseful(response)) {
      await cache.put(key, response.clone());
      return response;
    }
    if (response.status < 500) return response;
  } catch {
    // Fall through to the last successful response.
  }
  const cached = await cache.match(key);
  if (!cached) return Response.error();
  const headers = new Headers(cached.headers);
  headers.set("X-Acron-Offline", "1");
  return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    if (request.method === "POST" && new URL(request.url).pathname === "/api/auth/logout") {
      event.waitUntil(Promise.all([
        caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("acron-private-"))
          .map((key) => caches.delete(key)))),
        caches.open(META_CACHE).then((cache) => cache.delete(META_URL)),
      ]));
    }
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(caches.open(STATIC_CACHE).then(async (cache) => {
      const hit = await cache.match(request);
      if (hit && self.location.hostname !== "localhost") return hit;
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        return hit || Response.error();
      }
    }));
    return;
  }

  const isPrivateApi = url.pathname.startsWith("/api/proxy/") && !url.pathname.startsWith("/api/proxy/auth/");
  const isAppDocument = url.pathname === "/app" || url.pathname.startsWith("/app/");
  const isAppNavigation = isAppDocument && (request.mode === "navigate" || request.headers.get("RSC") === "1");
  if (!isPrivateApi && !isAppNavigation) return;

  event.respondWith((async () => {
    const organizationId = await currentOrganizationId();
    if (!organizationId) return fetch(request);
    const cacheName = `acron-private-${organizationId}`;
    const key = scopedKey(request, organizationId);
    if (isPrivateApi) {
      return cachedNetworkFirst(request, cacheName, key, (response) =>
        response.ok && response.headers.get("content-type")?.includes("application/json") &&
        !response.headers.get("cache-control")?.includes("no-store"),
      );
    }

    try {
      const response = await fetch(request);
      const unavailable = response.headers.get("X-Acron-Offline-Unavailable") === "1" ||
        (response.ok && (await response.clone().text()).includes("data-acron-offline-unavailable"));
      if (!unavailable && response.ok) {
        await (await caches.open(cacheName)).put(key, response.clone());
        return response;
      }
    } catch {
      // Serve the last workspace-scoped document or RSC payload.
    }
    const cached = await (await caches.open(cacheName)).match(key);
    if (!cached) return Response.error();
    const headers = new Headers(cached.headers);
    headers.set("X-Acron-Offline", "1");
    return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers });
  })());
});
