import assert from "node:assert/strict";
import test from "node:test";
import { enqueueOfflineMutation } from "./offline-mutations.ts";

function mockDatabase(abort) {
  let closed = false;
  globalThis.indexedDB = {
    open() {
      const open = {};
      const db = {
        close() { closed = true; },
        transaction() {
          const tx = {
            objectStore() {
              return {
                add() {
                  const request = { result: "saved" };
                  queueMicrotask(() => {
                    request.onsuccess();
                    if (abort) tx.onabort();
                    else tx.oncomplete();
                  });
                  return request;
                },
              };
            },
          };
          return tx;
        },
      };
      queueMicrotask(() => { open.result = db; open.onsuccess(); });
      return open;
    },
  };
  return () => closed;
}

test("offline payment is reported saved only after the transaction commits", async () => {
  const closed = mockDatabase(false);
  let announcements = 0;
  globalThis.window = { dispatchEvent() { announcements += 1; } };
  await enqueueOfflineMutation({ organizationId: "gym", path: "/cash/log", body: {}, idempotencyKey: "key" });
  assert.equal(closed(), true);
  assert.equal(announcements, 1);
});

test("an aborted transaction does not report an offline payment as saved", async () => {
  const closed = mockDatabase(true);
  let announcements = 0;
  globalThis.window = { dispatchEvent() { announcements += 1; } };
  await assert.rejects(enqueueOfflineMutation({ organizationId: "gym", path: "/cash/log", body: {}, idempotencyKey: "key" }), /aborted/);
  assert.equal(closed(), true);
  assert.equal(announcements, 0);
});
