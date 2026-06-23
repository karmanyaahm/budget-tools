// File System Access API helpers with IndexedDB handle persistence.
// Falls back gracefully; the plain <input type=file> path always works.

const DB_NAME = "budgetPieFS";
const STORE = "handles";
const HKEY = "dbfile";

function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB_NAME, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}

export function supportsFS() {
  return "showOpenFilePicker" in window;
}

export async function pickFile() {
  const [h] = await window.showOpenFilePicker({
    types: [{
      description: "Buckets / SQLite database",
      accept: { "application/octet-stream": [".buckets", ".sqlite", ".db", ".buckets-journal"] },
    }],
  });
  return h;
}

export async function readHandle(h) {
  const f = await h.getFile();
  return { bytes: new Uint8Array(await f.arrayBuffer()), name: f.name };
}

export async function ensurePermission(h, interactive) {
  const opts = { mode: "read" };
  if ((await h.queryPermission(opts)) === "granted") return true;
  if (!interactive) return false;
  return (await h.requestPermission(opts)) === "granted";
}

export async function saveHandle(h) {
  try {
    const db = await idb();
    await new Promise((res, rej) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(h, HKEY);
      tx.oncomplete = res; tx.onerror = () => rej(tx.error);
    });
  } catch (e) { console.warn("saveHandle failed", e); }
}

export async function loadHandle() {
  try {
    const db = await idb();
    return await new Promise((res) => {
      const tx = db.transaction(STORE, "readonly");
      const rq = tx.objectStore(STORE).get(HKEY);
      rq.onsuccess = () => res(rq.result || null);
      rq.onerror = () => res(null);
    });
  } catch { return null; }
}
