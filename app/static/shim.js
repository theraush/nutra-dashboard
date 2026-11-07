// Gives the dashboard the same window.claude.use('db' | 'user') interface it has on claude.ai,
// backed by this site's own /api/db. Changes from other people show up within ~20 seconds.
(function () {
  const ME = window.NUTRA_ME || null;
  let docs = new Map(); // path -> {data, version}
  const subs = new Set();
  let timer = null, inflight = null;

  const parent = p => p.split('/').slice(0, -1).join('/');
  const snapDoc = p => {
    const d = docs.get(p);
    return { id: p.split('/').pop(), exists: !!d, data: () => d ? JSON.parse(JSON.stringify(d.data)) : undefined,
      metadata: { fromCache: false, hasPendingWrites: false } };
  };
  const snapCol = c => {
    const list = [...docs.keys()].filter(p => parent(p) === c).sort().map(snapDoc);
    return { docs: list, size: list.length, empty: !list.length, metadata: { fromCache: false, hasPendingWrites: false }, docChanges: () => [] };
  };

  async function api(body) {
    const r = await fetch('/api/db', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify(body) });
    if (r.status === 401) { location.href = '/login'; throw new Error('signed out'); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) { const e = new Error(j.error || ('error ' + r.status)); e.code = j.code || r.status; throw e; }
    return j;
  }
  async function poll() {
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const j = await api({ op: 'all' });
        const next = new Map();
        for (const d of j.docs) next.set(d.path, { data: d.data, version: d.version });
        const changed = new Set();
        for (const [p, d] of next) { const o = docs.get(p); if (!o || o.version !== d.version) changed.add(p); }
        for (const p of docs.keys()) if (!next.has(p)) changed.add(p);
        docs = next;
        if (changed.size || !poll.first) { poll.first = true; for (const s of subs) s(changed, true); }
      } catch (e) { for (const s of subs) s(null, false, e); }
      finally { inflight = null; }
    })();
    return inflight;
  }
  function start() { if (!timer) { timer = setInterval(() => { if (!document.hidden) poll(); }, 20000); poll(); } }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && timer) poll(); });

  function docRef(path) {
    return {
      id: path.split('/').pop(), path,
      async get() { await poll(); return snapDoc(path); },
      async set(data) { await api({ op: 'set', path, data }); await poll(); },
      async update(data) { await api({ op: 'update', path, data }); await poll(); },
      async delete() { await api({ op: 'delete', path }); await poll(); },
      onSnapshot(next, err) {
        const f = (changed, ok, e) => { if (!ok) { err && err(e); return; } if (!changed || changed.has(path) || !f.fired) { f.fired = true; next(snapDoc(path)); } };
        subs.add(f); start(); if (docs.size || poll.first) f(new Set([path]), true);
        return () => subs.delete(f);
      }
    };
  }
  function colRef(c) {
    return {
      path: c,
      doc: id => docRef(c + '/' + (id || Math.random().toString(36).slice(2, 12))),
      async add(data) { const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8); await api({ op: 'set', path: c + '/' + id, data }); await poll(); return docRef(c + '/' + id); },
      async get() { await poll(); return snapCol(c); },
      onSnapshot(next, err) {
        const f = (changed, ok, e) => { if (!ok) { err && err(e); return; } if (!changed || !f.fired || [...changed].some(p => parent(p) === c)) { f.fired = true; next(snapCol(c)); } };
        subs.add(f); start(); if (poll.first) f(null, true);
        return () => subs.delete(f);
      }
    };
  }
  const dbApi = { doc: docRef, collection: colRef };
  const userApi = { me: async () => ME ? { id: ME.id, email: ME.email, name: ME.name, isOwner: ME.role === 'owner', canEdit: ME.role === 'owner' || ME.role === 'editor' } : null };
  window.claude = { use: async n => n === 'db' ? dbApi : n === 'user' ? userApi : null };
})();
