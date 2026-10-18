import assert from "node:assert/strict";

const origin = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100";

for (const route of ["/", "/login"]) {
  const response = await fetch(new URL(route, origin), { redirect: "manual" });
  assert.equal(response.status, 200, `${route} should serve successfully (got ${response.status})`);
  await response.arrayBuffer();
}

const protectedResponse = await fetch(new URL("/app", origin), { redirect: "manual" });
assert.equal(protectedResponse.status, 307, `/app should redirect without a session (got ${protectedResponse.status})`);
const destination = new URL(protectedResponse.headers.get("location"), origin);
assert.equal(destination.pathname, "/login", "/app should send unauthenticated users to login");
assert.equal(destination.searchParams.get("next"), "/app", "login redirect should preserve the requested page");

console.log("Production smoke checks passed: public pages and protected-route redirect.");
