"use client";

export type OfflineMutation = {
  id: string;
  organizationId: string;
  path: string;
  body: unknown;
  idempotencyKey: string;
  createdAt: string;
  state: "queued" | "failed";
  error?: string;
};

const DATABASE = "acron-offline-operations";
const STORE = "mutations";
const CHANGE_EVENT = "acron:offline-queue-changed";

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("organizationId", "organizationId");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open offline queue."));
  });
}

function transact<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDatabase().then((db) => new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = run(tx.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline queue operation failed."));
    tx.oncomplete = () => db.close();
    tx.onerror = () => { db.close(); reject(tx.error ?? new Error("Offline queue transaction failed.")); };
  }));
}

function announce() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export async function listOfflineMutations(organizationId: string): Promise<OfflineMutation[]> {
  const rows = await transact<OfflineMutation[]>("readonly", (store) => store.index("organizationId").getAll(organizationId));
  return rows.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function enqueueOfflineMutation(input: Omit<OfflineMutation, "id" | "createdAt" | "state">): Promise<void> {
  // Only known, idempotent business operations may be persisted for replay.
  const supported = input.path === "/cash/log" || /^\/leads\/[a-f0-9-]+\/bookings$/i.test(input.path);
  if (!supported) throw new Error("This action cannot be queued for offline sync.");
  const row: OfflineMutation = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    state: "queued",
  };
  await transact<IDBValidKey>("readwrite", (store) => store.add(row));
  announce();
}

export async function updateOfflineMutation(row: OfflineMutation): Promise<void> {
  await transact<IDBValidKey>("readwrite", (store) => store.put(row));
  announce();
}

export async function removeOfflineMutation(id: string): Promise<void> {
  await transact<undefined>("readwrite", (store) => store.delete(id));
  announce();
}

export const OFFLINE_QUEUE_CHANGE_EVENT = CHANGE_EVENT;
