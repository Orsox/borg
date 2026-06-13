# Peer Sync

Connect a BorgOS instance to **another local BorgOS instance** and synchronize Archon
**workflows, skills and agents** plus the **Skill DB module** — safely, with a static
diff, a Seven-of-Nine semantic review, and manual per-item approval.

Installing BorgOS on a second machine no longer means re-creating everything by hand.

---

## How it works

```
Local BorgOS (client)                         Remote BorgOS (peer, read-only)
─────────────────────                         ───────────────────────────────
start_sync()  ───────────────HTTP GET───────►  /api/peer/manifest  (bearer PEER_SYNC_TOKEN)
      │                                            returns SyncableItem[]
      ▼
compute_diff(local, remote)   → only_remote / only_local / changed / identical
      │  (changed items)
      ▼
SyncComparatorDrone.compare()  → Seven analyses each changed item (direct LLM)
      │
      ▼
/sync UI  → you Accept / Reject each item
      │
      ▼
apply_item()  → write to local ARCHON_PATH / skills DB + re-scan + audit
```

**Topology: pull + review.** The remote only ever exposes a single read-only endpoint.
Your local instance pulls from it, computes the differences, and writes nothing until you
explicitly accept an item. The remote is never modified.

---

## Concepts

### SyncableItem — one shape for four scopes

Everything that can be synced is normalized into a single shape so diff/compare/apply are
written once:

| Field          | Meaning                                                              |
|----------------|----------------------------------------------------------------------|
| `kind`         | `workflow` \| `skill` \| `agent` \| `skill_db`                        |
| `identity`     | Stable, cross-machine ID (see below)                                  |
| `name`         | Human-readable label                                                  |
| `content`      | Raw text (YAML/JSON for assets; canonical metadata JSON for skill_db) |
| `content_hash` | `sha256(content)` — the basis for the static diff                    |

**Identity** is deliberately machine-independent:
- Archon assets (`workflow`/`skill`/`agent`): the POSIX path **relative to `ARCHON_PATH`**
  (e.g. `workflows/demo.yaml`), since the absolute path differs per host.
- `skill_db`: the normalized skill **name**.

For `skill_db` the synced `content` is the skill's **metadata** (name, description, model,
category, tags) — the source of truth — not the generated workflow YAML. Applying therefore
recreates the skill faithfully through the normal `skills` service.

### Static diff

`diff.py::compute_diff()` is a pure function. It indexes both manifests by
`(kind, identity)` and classifies each key:

| Status        | Meaning                                          | Applyable |
|---------------|--------------------------------------------------|-----------|
| `only_remote` | Exists on the peer, not locally                  | ✅ adds it |
| `only_local`  | Exists locally, not on the peer                  | ❌ nothing to pull |
| `changed`     | Exists on both, content hashes differ            | ✅ overwrites local |
| `identical`   | Same on both — not persisted                      | —         |

### Seven of Nine's comparison agent

Only **changed** items are ambiguous, so they go to Seven's specialized
`SyncComparatorDrone` (`seven_of_nine/sync_agent.py`). It runs a **direct LLM call** (no
sandbox/Docker — the task is pure text reasoning) and produces, per item:

- **semantic_compare** — what actually differs (beyond a textual diff)
- **merge_recommendation** — which side should win (`local` / `remote` / `merge`) + notes
- **risk_assessment** — breaking-change / safety call before adopting foreign content

These three skills are also seeded as visible `Skill` rows (`category sync-comparison`,
tagged `seven`) so they appear in the Skills UI as Seven's toolkit. Every comparison and
every apply writes a `DroneAuditEntry`.

---

## Setup

### 1. Make an instance available as a peer (the "server" side)

Set a bearer token in `backend/.env` on the instance you want to sync **from**:

```env
PEER_SYNC_TOKEN=some-long-random-secret
```

Empty (the default) ⇒ `/api/peer/manifest` returns **403** and the instance refuses to act
as a peer. The token gates the only endpoint that exposes asset content across machines; it
is **not** the JWT user session (the calling instance has no user there).

### 2. Register the peer (the "client" side)

In the other instance's UI, open **Peer Sync** (`/sync`) and add a peer:

- **Label** — any name, e.g. `Workstation`
- **Base URL** — the peer's API root, e.g. `http://192.168.1.50:1742`
- **Peer token** — the `PEER_SYNC_TOKEN` you set in step 1

### 3. Sync

1. Click **Sync** on the peer → the static diff runs and the items appear, grouped by status.
2. Click **Compare with Seven** → Seven analyses the `changed` items.
3. Expand any item to see Seven's analysis and a side-by-side local/remote view.
4. **Accept & Apply** to adopt the remote version, or **Reject** to keep yours.

---

## API

### Peer-facing (token-gated, read-only)

| Method | Path                  | Auth                 | Description                        |
|--------|-----------------------|----------------------|------------------------------------|
| GET    | `/api/peer/manifest`  | `Bearer PEER_SYNC_TOKEN` | This instance's `SyncableItem[]` |

### Client-facing (JWT-guarded)

| Method | Path                                | Description                          |
|--------|-------------------------------------|--------------------------------------|
| GET    | `/api/peer-sync/peers`              | List registered peers                |
| POST   | `/api/peer-sync/peers`              | Register a peer (`label`, `base_url`, `token`) |
| DELETE | `/api/peer-sync/peers/{id}`         | Remove a peer                        |
| POST   | `/api/peer-sync/peers/{id}/sync`    | Pull manifest + static diff → SyncRun |
| POST   | `/api/peer-sync/runs/{id}/compare`  | Run Seven's comparator over changed items |
| GET    | `/api/peer-sync/runs/{id}`          | Run + items + analyses               |
| POST   | `/api/peer-sync/items/{id}/decision`| `accept` / `reject`                  |
| POST   | `/api/peer-sync/items/{id}/apply`   | Write the accepted remote version locally |

---

## Data model

- **`PeerInstance`** — a registered remote (`label`, `base_url`, `token`, `last_synced_at`).
  `token` is the *remote's* `PEER_SYNC_TOKEN`, sent as bearer when pulling.
- **`SyncRun`** — one diff session against a peer (`status`, `counts_json`), so the review
  survives a page reload.
- **`SyncItemRecord`** — one differing item: `kind`, `identity`, `status`, both hashes, both
  contents, Seven's `analysis_json`, and the operator `decision`
  (`pending` → `accepted`/`rejected` → `applied`).

New tables only — created by `Base.metadata.create_all`; no migration needed.

---

## Safety notes

- **Pull only.** A peer is never written to; only its manifest is read.
- **Manual apply.** Writing a remote version to disk / the skills DB is the single mutating
  step and is gated behind your per-item **Accept**.
- **Path-traversal guard.** Asset writes are confined to `ARCHON_PATH`; a remote `identity`
  that tries to escape it is rejected.
- **Audited.** Every compare and apply is recorded as a `DroneAuditEntry` under Seven.
- **Local by design.** Manifests carry full asset content — intended for instances on the
  same trusted local network.

---

## Files

```
backend/app/peer_sync/
  manifest.py    build_local_manifest() + identity/hash helpers
  diff.py        compute_diff() — pure static diff
  client.py      PeerClient / PeerUnavailable
  service.py     start_sync, run_comparison, apply_item, peer CRUD
  router.py      /api/peer-sync (JWT)
  peer_router.py /api/peer/manifest (PEER_SYNC_TOKEN)
  models.py      PeerInstance, SyncRun, SyncItemRecord
  schemas.py     SyncableItem, DiffItem, request/response models

backend/app/seven_of_nine/sync_agent.py   SyncComparatorDrone + seed_sync_skills
frontend/src/lib/api/peerSync.ts           typed client
frontend/src/routes/sync/+page.svelte      review UI

Tests: backend/tests/test_peer_sync_diff.py, test_peer_sync_manifest.py, test_sync_agent.py
```
