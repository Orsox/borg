# Locutus Autonomy Transition Plan

Date: 2026-06-07
Status: Proposal — for review, not yet executed
Scope: `backend/app/locutus/`, `backend/app/discord_bot/`, `backend/app/skills/`, `backend/app/dreaming/`, `backend/app/task_automation/`

## Context

Locutus already has the *data model* for autonomy (`ReasoningLog`, `EvolutionBudget`,
`SkillRecord`, `CharacterMemoryEntry`, `DreamingRun`, `task_type="heartbeat"`) but no
process actually drives it. The dreaming consolidation runs only on manual trigger,
gap analysis is unimplemented, skill creation is never auto-triggered, and there is no
audit trail or approval gate for autonomous actions.

This plan closes that loop in five small, independently shippable stages, ordered so
that each stage produces an observable, testable result before the next one builds on
it. Sandboxing (per `thoughts/borg-os-llm-sandbox-hardening-idea.md`) is deliberately
pushed to the end — it should wrap a *working* skill-execution loop, not be built ahead
of one.

Guiding constraint (from Soul/Rules, ADVISOR mode): Locutus drafts and proposes; it does
not act unsupervised on anything irreversible. Every stage below preserves a human
approval point before an action with lasting effect (file writes outside its sandboxed
root, skill creation, skill execution).

---

## Stage 0 — Audit trail (foundation for everything else)

**Goal:** Every autonomous read/write Locutus performs is logged in an append-only,
queryable record before any new autonomous behavior is added.

**Why first:** Cheaper to build now while the action surface is small (chat, search,
note creation, character-file writes). Retrofitting later, once skill execution exists,
means reconstructing history you never captured.

**Steps:**
1. Add `LocutusAuditEntry` model in `backend/app/locutus/models.py`:
   `id, run_id, actor ("locutus"|"user"), action, target, payload_summary, result ("ok"|"error"|"denied"), created_at`.
2. Add a thin `record_action(...)` helper in `locutus/service.py`; call it from every
   existing mutating path: `update_character_profile`, `create_character_memory`,
   `archive_character_memory`, `write_character_file`, and from
   `discord_bot/service.py.create_note`.
3. Add a paginated `GET /api/locutus/audit` endpoint (reuse the pagination pattern
   already used for `/memory`).

**Acceptance criteria:**
- [ ] Every call to the five instrumented service functions produces exactly one
      `LocutusAuditEntry` row, verified by a unit test per function (assert row count
      delta == 1, fields populated).
- [ ] `GET /api/locutus/audit` returns entries newest-first, paginated, filterable by
      `actor` and `action`, and requires `get_current_user()` like other Locutus routes.
- [ ] No existing test in `test_discord_bot.py` / Locutus test suite regresses.

---

## Stage 1 — Heartbeat scheduling (turn "can run" into "does run")

**Goal:** Dreaming consolidation and (later) gap analysis run periodically without
manual triggering, on a schedule the user can see and adjust.

**Steps:**
1. In `task_automation/`, add a default seeded `Task` with `task_type="heartbeat"` and
   `heartbeat_workflow_name` pointing at a new internal handler (not an Archon workflow
   path) — e.g. `locutus.heartbeat.dreaming_cycle`.
2. Extend the scheduler (`task_automation/scheduler.py`) to recognize this internal
   handler and invoke `dreaming.service.run_consolidation_cycle()` directly, reusing
   the existing `sse_queue` to emit `dreaming_run_started` / `dreaming_run_completed`
   events (these already exist per the SSE event type list).
3. Make the interval configurable via env var (`LOCUTUS_HEARTBEAT_INTERVAL_MINUTES`,
   default e.g. 360 = every 6h) and surfaced in `BotConfig`/settings, not hardcoded.
4. Confirm `discord_bot/listener.py` already converts these events into Discord
   notifications (per the existing `TaskEventListener` — verify, don't re-implement).

**Acceptance criteria:**
- [ ] On backend startup, exactly one heartbeat `Task` for dreaming exists (idempotent
      seeding — re-running startup does not create duplicates).
- [ ] With the interval set to a short value in a test environment, a dreaming run is
      triggered automatically without any manual API call, and a `DreamingRun` row with
      `status="completed"` (or `"failed"`, with error captured) appears.
- [ ] A `dreaming_run_started`/`dreaming_run_completed` pair is observable on the
      `/api/tasks/stream` SSE endpoint and a corresponding Discord notification is sent
      (manually verified once against a test Discord channel; automated test asserts the
      listener receives and formats the event).
- [ ] Interval is read from config, documented in `.env.example` / `config.py`.

---

## Stage 2 — Gap analysis → ReasoningLog (give the loop something to reason about)

**Goal:** Recurring problems detected during dreaming are turned into concrete,
human-readable proposals (`ReasoningLog`, `status="draft"`) instead of being lost in
the Dream Diary prose.

**Steps:**
1. Implement `GapAnalysisRequest`/`SkillGap` (already defined in `locutus/schemas.py`
   but unused) as a real function in `dreaming/service.py` or a new
   `locutus/gap_analysis.py`: scan the REM-phase pattern output (tag frequency, recurring
   errors, status distributions already computed) for patterns that cross a defined
   threshold (e.g. same error category ≥ N times in 14 days).
2. For each qualifying gap, create exactly one open `ReasoningLog` (dedupe by
   `trigger_description` hash so repeated dreaming cycles don't spam duplicates) with
   `title`, `trigger_description`, `proposed_solution` (LLM-drafted via the existing
   `LlmClient`), `expected_outcome`, `status="draft"`.
3. Wire this as the final step of the heartbeat dreaming cycle from Stage 1 — gap
   analysis runs automatically after each consolidation.
4. Add a Discord notification (reuse `TaskNotification` formatting) summarizing new
   draft `ReasoningLog`s, so the user sees proposals without opening the UI.

**Acceptance criteria:**
- [ ] Given a seeded set of `ActionMemory` entries containing a repeated failure
      pattern (test fixture), running the gap-analysis step produces exactly one
      `ReasoningLog` with `status="draft"` and non-empty `proposed_solution`.
- [ ] Running gap analysis twice over the same data does not create a duplicate
      `ReasoningLog` (dedupe verified by a test asserting row count stays at 1).
- [ ] A Discord message is sent listing newly created draft `ReasoningLog`s with
      title + trigger description (verified via listener/notification unit test).
- [ ] No `ReasoningLog` is auto-approved or acted upon — `status` remains `"draft"`
      until a human changes it (enforced by the absence of any code path that writes
      `status="approved"` outside the explicit approval endpoint built in Stage 3).

---

## Stage 3 — Approval gate (the ADVISOR boundary, made explicit in code)

**Goal:** A `ReasoningLog` can move from `draft` to `approved` (and only then trigger
downstream action) exclusively through an explicit, auditable human decision — never
automatically.

**Steps:**
1. Add `POST /api/locutus/reasoning/{id}/decision` with body `{"decision": "approve"|"reject", "note": str | None}`.
   - `approve` → `status="approved"`, records decision in `LocutusAuditEntry`
     (`actor="user"`).
   - `reject` → `status="rejected"`, same audit record.
2. Add `GET /api/locutus/reasoning?status=draft` so drafts are listable (paginated,
   reuse existing list patterns).
3. Extend the Discord notification from Stage 2 to include the `ReasoningLog` id and a
   short instruction for how to approve/reject (initially: via the BorgOS UI/API — a
   Discord-side approve/reject command can be a fast-follow, not required for this
   stage).
4. Enforce server-side: `EvolutionBudget` is checked and decremented at *approval* time,
   not at proposal time — so drafts don't consume budget, only acted-upon proposals do.

**Acceptance criteria:**
- [ ] A `draft` `ReasoningLog` cannot reach `approved`/`rejected` through any code path
      except the new decision endpoint (verified by grep/review — no other writer of
      `ReasoningLog.status` exists outside this endpoint and the seed/creation paths).
- [ ] Calling the decision endpoint produces a `LocutusAuditEntry` with `actor="user"`
      and the chosen decision.
- [ ] Approving a `ReasoningLog` when `EvolutionBudget.skills_created >= max_skills_per_week`
      returns an error and leaves `status="draft"` (budget enforced at approval, tested
      with a fixture budget at its limit).
- [ ] Approving within budget increments `EvolutionBudget.skills_created` exactly once
      and transitions status to `approved`.

---

## Stage 4 — Skill creation from approved proposals (close the loop)

**Goal:** An `approved` `ReasoningLog` results in a generated skill file, a linked
`SkillRecord`, and a final notification — with no further manual steps, but also no
execution of the skill yet (creation ≠ execution; see Stage 5 for the sandboxed
execution boundary).

**Steps:**
1. Add a handler triggered on `ReasoningLog.status` transitioning to `approved`
   (simplest: a check inside the decision endpoint from Stage 3, not a separate poller)
   that calls the existing `skills/yaml_generator.py` to draft a skill YAML from
   `proposed_solution` + `expected_outcome`.
2. Validate the generated YAML using the existing hardened validation from commit
   `a065dda` before writing to disk.
3. Create a `SkillRecord` (`status="draft"`, `reasoning_log_id` set, `file_path` set)
   and update `ReasoningLog.created_skill_path`.
4. Notify via Discord: "Skill `<name>` drafted from proposal #<id>, awaiting review at `<path>`."
5. Skill remains `status="draft"` — a separate, explicit action (existing skill-review
   UI/endpoint, or a new minimal one) promotes it to `active`. This plan does not expand
   scope to building that promotion flow if it doesn't already exist; it only ensures
   `SkillRecord` is correctly populated and visible.

**Acceptance criteria:**
- [ ] Approving a `ReasoningLog` (from Stage 3) results in exactly one new YAML file on
      disk that passes the existing validator, one `SkillRecord` row with
      `status="draft"` and correct `reasoning_log_id` FK, and
      `ReasoningLog.created_skill_path` populated.
- [ ] If YAML validation fails, no file is written, no `SkillRecord` is created, the
      `ReasoningLog` stays `approved` (not silently advanced), and the failure is both
      logged to `LocutusAuditEntry` (`result="error"`) and reported via Discord.
- [ ] A Discord notification names the skill, the originating proposal id, and the file
      path.
- [ ] End-to-end test: seed `ActionMemory` with a repeating failure → run heartbeat
      cycle → approve resulting `ReasoningLog` via API → assert skill file + `SkillRecord`
      + notification all materialize, in that order, traceable via `LocutusAuditEntry`.

---

## Stage 5 — Scoped sandbox for skill *execution* (not for Locutus itself)

**Goal:** Generated skills can be executed without risking the host, using the minimum
viable slice of `thoughts/borg-os-llm-sandbox-hardening-idea.md` — scoped to skill
execution only, not a general-purpose agent sandbox.

**Why scoped, why last:** Today nothing in Locutus executes arbitrary/generated code —
chat, search, note creation, and character-file writes are all narrow, fixed operations
under a known root. Sandboxing the whole Locutus process would be effort spent isolating
behavior that doesn't need isolation. Once Stage 4 produces real generated skills,
*executing* them is the first point where arbitrary code enters the picture — that's the
actual boundary to defend.

**Steps:**
1. New minimal module `backend/app/agent_sandbox/` (per the existing thoughts doc's
   Phase 1 sketch), but reduced to exactly: create ephemeral worktree → run one skill
   invocation in a locked-down container (`--network=none`, `--cap-drop=ALL`,
   `--read-only`, resource limits per the doc's example) → capture stdout/stderr/exit
   code/diff → tear down.
2. No policy engine yet (Phase 2 of the doc) — hard-code the deny-list from the doc
   (`sudo`, `mount`, `curl|sh`, `~/.ssh` access, etc.) as a pre-execution static check
   on the skill's command list; reject with a clear error if violated.
3. Skill execution requires the skill to already be `status="active"` (i.e., a human
   has reviewed and promoted it per Stage 4) — execution is never triggered from
   `status="draft"`.
4. Every execution produces a `LocutusAuditEntry` (`action="skill_execution"`,
   `payload_summary` = command + truncated output, `result`).

**Acceptance criteria:**
- [ ] Executing an `active` skill runs inside a container with `--network=none`,
      `--cap-drop=ALL`, `--read-only`, and explicit CPU/memory/pids limits — verified by
      inspecting the constructed `docker run` invocation in a unit test (mocking the
      actual `docker` call).
- [ ] A skill whose command list matches any deny-list pattern is rejected before
      container start, with `result="denied"` recorded in `LocutusAuditEntry` and no
      container created.
- [ ] Attempting to execute a `draft` or `deprecated` skill is rejected at the API/service
      layer (status check), with no container created.
- [ ] After execution, exactly one `LocutusAuditEntry` captures command, truncated
      output, exit status, and a reference to the worktree/diff artifact location.
- [ ] Worktree and container are removed after the run completes (or are clearly
      retained under a documented retention policy if the user opts to keep them for
      review) — no orphaned containers/worktrees after a test run.

---

## Sequencing summary

```
Stage 0  Audit trail            ─┐
Stage 1  Heartbeat scheduling    │  each stage ships independently,
Stage 2  Gap analysis → drafts   │  is observable via SSE/Discord,
Stage 3  Approval gate           │  and is covered by its own tests
Stage 4  Skill creation          │  before the next stage starts
Stage 5  Scoped skill sandbox  ─┘
```

Each stage can be its own PR/branch and reviewed independently. Stages 0–3 require no
new infrastructure (containers, worktrees) — they're pure backend logic on top of
existing models, the existing scheduler, and the existing SSE/Discord notification path.
Stage 4 only touches the filesystem under the already-validated skill-generation path.
Stage 5 is the only stage that introduces new infrastructure (Docker), and by the time
it starts, stages 0–4 will have already produced an audit trail, an approval boundary,
and a budget mechanism that the sandbox can plug into rather than needing to invent.

## Out of scope for this plan

- General-purpose agent sandboxing for Locutus's own process (chat/search/notes do not
  execute arbitrary code and don't need isolation).
- Web broker / Firecrawl integration (Phase 4 of the hardening doc) — irrelevant until
  Locutus or its skills need external network access, which Stage 5's `--network=none`
  default explicitly defers.
- Multi-agent orchestration, agent creation (`EvolutionBudget.max_agents_per_week`) —
  not addressed; revisit only after the skill loop (Stages 2–5) is proven stable.
