# Orsox's Second Brain — Product Requirements Document

**Generated:** 2026-05-17
**Owner:** Orsox (Mega-Power-Engineer, Berlin / CET)
**Summary:** A proactive AI workspace assistant for an AI-focused engineer — monitoring Jira tickets, Teams messages, and GitLab activity across projects, with actionable drafts surfaced for review and never sent automatically (Advisor mode).

---

## Quick Reference

| Setting | Value |
|---|---|
| Proactivity | **Advisor** — drafts for review, never auto-sends |
| Timezone | Berlin (CET = UTC+1, CEST = UTC+2) |
| OS | Linux |
| Deployment | Local + VPS |
| Vector DB | SQLite + sqlite-vec (local), Postgres + pgvector (VPS) |
| Embedder | FastEmbed `all-MiniLM-L6-v2`, 384-dim |

---

## Phase 1: Foundation (Memory Layer)

**What to build:** The Obsidian vault structure and core memory files that ground every future conversation. Obsidian is just the Markdown viewer — the real value is the files themselves.

**Key files to create:**

```
~/Memory/
  SOUL.md           ← Agent personality, rules, Berlin timezone, Advisor limits
  USER.md           ← Orsox's profile, all integration endpoints/IDs
  MEMORY.md         ← Key decisions, active projects, team context (keep <3KB)
  HABITS.md         ← 5 daily pillars: AI Learning, Agent Shipping, Team Awareness, Deep Work, Health
  HEARTBEAT.md      ← Monitor checklist: what to watch across integrations
  daily/            ← YYYY-MM-DD.md, append-only timestamped logs
  meetings/         ← Meeting notes and decisions
  projects/         ← AI agent project status files
  team-context/     ← Who does what, timezones, repo ownership
  drafts/
    active/         ← Heartbeat-generated drafts awaiting Orsox's review
    sent/           ← Confirmed/used drafts (for voice-matching via RAG)
    expired/        ← Auto-archived after 24h with no action
```

**SOUL.md key contents:**
```markdown
# Orsox's Agent — Soul
- Timezone: Berlin (CET/CEST). Use local time in all outputs.
- Style: terse, technical, no fluff. Prefer bullet points over prose.
- Focus: AI engineering, agent development, LLM tooling.
- Proactivity: ADVISOR. Draft everything, send nothing.
- Hard limits: Never send Teams messages. Never post anywhere. Never delete files.
  Never write outside ~/Memory/. Never access financial APIs.
```

**USER.md key fields to fill in:**
```markdown
# User Profile
Name: Orsox
Role: Mega-Power-Engineer
Timezone: Berlin (UTC+1/UTC+2)

# Jira
JIRA_URL: https://yourcompany.atlassian.net   # or self-hosted URL
JIRA_PROJECT_KEYS: [AI, AGENT, ...]           # your active projects

# GitLab
GITLAB_URL: https://gitlab.com                # or self-hosted
GITLAB_MY_NAMESPACES: [orsox, yourcompany/ai-team]

# Teams
AZURE_TENANT_ID: ...
TEAMS_USER_ID: ...

# Polarion
POLARION_URL: https://polarion.yourcompany.com
POLARION_PROJECT_IDS: [...]

# OneDrive
ONEDRIVE_ROOT_PATH: /drives/me/root
```

**Dependencies:** None — this is the foundation.
**Estimated complexity:** Low
**Personalization notes:** MEMORY.md categories map directly to Orsox's choices: meeting notes & decisions, project status (AI agent projects), personal goals & habits, content ideas & drafts, team context. Start MEMORY.md with your 2-3 most active projects and key team members.

---

## Phase 2: Hooks (Context Persistence)

**What to build:** Three Claude Code lifecycle hooks that inject your memory into every session and flush new learnings back to the vault automatically — so you never lose a decision or architectural insight.

**Key files:**
- `.claude/hooks/session-start-context.py` — Reads SOUL.md + USER.md + MEMORY.md + last 3 daily logs → prints to stdout → Claude Code injects as system context
- `.claude/hooks/pre-compact-flush.py` — Before auto-compaction, reads JSONL transcript → extracts decisions/tasks/insights → appends to `daily/YYYY-MM-DD.md`
- `.claude/hooks/session-end-flush.py` — On session end, appends conversation summary to daily log
- `.claude/settings.json` — Hook registration

**`.claude/settings.json` hook configuration:**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "python3 .claude/hooks/session-start-context.py" }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "python3 .claude/hooks/pre-compact-flush.py" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 .claude/hooks/session-end-flush.py" }
        ]
      }
    ]
  }
}
```

**How SessionStart works:**
```python
# session-start-context.py
import pathlib, datetime

VAULT = pathlib.Path.home() / "Memory"
now = datetime.datetime.now()

parts = []
for f in ["SOUL.md", "USER.md", "MEMORY.md", "HABITS.md"]:
    parts.append((VAULT / f).read_text())

# Load last 3 daily logs
for i in range(3):
    day = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
    p = VAULT / "daily" / f"{day}.md"
    if p.exists():
        parts.append(p.read_text())

# Morning habit nudge (06:00–10:00 CET)
if 6 <= now.hour <= 10:
    parts.append("\n[Morning check: review HABITS.md pillars for today]")

print("\n\n---\n\n".join(parts))
```

**Dependencies:** Phase 1.
**Estimated complexity:** Medium
**Personalization notes:** SessionStart loads HABITS.md during morning hours (06:00–10:00 CET) to surface today's pillars at the start of your workday. The pre-compact flush is especially important for Orsox — it captures AI architectural decisions and agent design notes that would otherwise be lost when long sessions compact.

---

## Phase 3: Memory Search (Hybrid RAG)

**What to build:** Index the entire Memory vault for hybrid vector + keyword search. Used by the heartbeat for context retrieval and by voice-matching when drafting Teams replies.

**Tech stack (VPS path — since you deploy Local + VPS):**
- **Vector store (VPS):** Postgres + pgvector
- **Keyword search (VPS):** tsvector + GIN index
- **Local fallback:** SQLite + sqlite-vec + FTS5
- **Embedder:** FastEmbed (ONNX, no GPU required)

**FastEmbed usage:**
```python
# embeddings.py
from fastembed import TextEmbedding

_model = None
def get_model():
    global _model
    if _model is None:
        # Downloads to ~/.cache/fastembed/ on first run (~22MB)
        _model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    return _model

def embed_batch(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_model().embed(texts)]  # embed() returns a generator
```

**Key files:**
- `.claude/scripts/embeddings.py` — Model singleton, `embed_batch(texts)`
- `.claude/scripts/db.py` — Abstraction: detects `DB_URL` env var → Postgres or SQLite; exposes `upsert_chunk()`, `vector_search()`, `keyword_search()`
- `.claude/scripts/memory_index.py` — Walk `~/Memory/`, chunk (~400 tokens, 50-token overlap), embed, upsert; mtime-based incremental re-indexing
- `.claude/scripts/memory_search.py` — CLI: `memory_search.py "jira triage approach"` → hybrid merge (0.7 vector + 0.3 keyword) → top-5 results; `--path-prefix drafts/sent` for voice-matching

**Hybrid search merge:**
```python
def hybrid_search(query: str, k=5) -> list[dict]:
    vec_results = vector_search(embed_batch([query])[0], k=k*2)
    kw_results = keyword_search(query, k=k*2)
    # RRF merge with weights
    scores = {}
    for rank, r in enumerate(vec_results):
        scores[r["id"]] = scores.get(r["id"], 0) + 0.7 / (rank + 1)
    for rank, r in enumerate(kw_results):
        scores[r["id"]] = scores.get(r["id"], 0) + 0.3 / (rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])[:k]
```

**VPS Postgres setup:**
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE memory_chunks (
    id TEXT PRIMARY KEY,
    path TEXT, content TEXT, embedding vector(384),
    ts_content tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX ON memory_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON memory_chunks USING GIN (ts_content);
```

**Dependencies:** Phase 1, Phase 9 (VPS Postgres setup).
**Estimated complexity:** Medium
**Personalization notes:** Index all 5 memory categories. Run `memory_index.py` via systemd timer every 6 hours on VPS, and on SessionStart locally (fast — only re-indexes changed files).

---

## Phase 4: Integrations (Obsidian → Jira → Polarion First)

All integrations follow this pattern: Python gathers data → sanitizes via `sanitize.py` → Claude reasons. Claude never sees API tokens.

### 4a: Obsidian (Priority 1)

**What to build:** Direct filesystem access to the vault — no API needed.

**Key files:**
- `.claude/scripts/integrations/obsidian.py`

```python
# Key functions
def list_recent(days=7) -> list[dict]:
    """Return notes modified in last N days with path + excerpt."""

def read_note(path: str) -> str:
    """Read a vault note by relative path."""

def append_to_daily(text: str):
    """Append timestamped entry to today's daily log."""

def search_title(query: str) -> list[str]:
    """Simple filename search across vault."""
```

**Auth:** None — filesystem only.
**Dependencies:** Phase 1.
**Estimated complexity:** Low

---

### 4b: Jira (Priority 2)

**What to build:** Fetch new and unassigned tickets from Orsox's projects, format a triage summary for review.

**Library:** `pip install atlassian-python-api`

**Auth:** PAT for Jira Data Center/Server; API Token for Jira Cloud.
Store in `.env`: `JIRA_URL`, `JIRA_TOKEN`, `JIRA_EMAIL` (Cloud only).

```python
# integrations/jira.py
from atlassian import Jira
import os

def get_client():
    # For Jira Data Center / Server (PAT):
    return Jira(url=os.environ["JIRA_URL"], token=os.environ["JIRA_TOKEN"])
    # For Jira Cloud (API token):
    # return Jira(url=..., username=os.environ["JIRA_EMAIL"],
    #             password=os.environ["JIRA_TOKEN"], cloud=True)

def get_new_tickets(project_keys: list[str]) -> list[dict]:
    """Fetch To Do / Open tickets created in last 3 days."""
    jql = f"project IN ({','.join(project_keys)}) AND status IN ('To Do','Open') AND created >= -3d ORDER BY created DESC"
    client = get_client()
    # IMPORTANT: use enhanced_jql for Cloud (handles nextPageToken pagination)
    # jql() is deprecated for Cloud
    results = client.enhanced_jql(jql, limit=50)
    return [{"key": i["key"], "summary": i["fields"]["summary"],
             "priority": i["fields"]["priority"]["name"],
             "assignee": i["fields"].get("assignee")} for i in results]

def triage_summary(tickets: list[dict]) -> str:
    """Format tickets as context block for Claude to reason over."""
    ...
```

**Rate limits:** 10 req/s (Cloud). Add `time.sleep(0.1)` between paginated calls.

**Key files:**
- `.claude/scripts/integrations/jira.py`
- Add to `.claude/scripts/query.py`: `query.py jira new`, `query.py jira triage`

**Dependencies:** Phase 1, Phase 8 (sanitize issue text).
**Estimated complexity:** Medium

---

### 4c: Polarion (Priority 3)

**What to build:** Read open work items and recent changes from Polarion projects.

**Library:** `pip install polarion-rest-api-client`

**Auth:** Polarion Personal Access Token (My Profile → Personal Access Tokens in Polarion UI).

```python
# integrations/polarion.py
from polarion_rest_api_client import OpenApiClient
import os

def get_project_client(project_id: str):
    client = OpenApiClient(
        polarion_url=os.environ["POLARION_URL"],
        token=os.environ["POLARION_TOKEN"]
    )
    return client.generate_project_client(project_id=project_id)

def get_open_requirements(project_id: str) -> list[dict]:
    pc = get_project_client(project_id)
    items = pc.get_work_items(query="type:requirement status:open")
    return [{"id": i.id, "title": i.title, "status": i.status} for i in items]

def get_recent_changes(project_id: str, days=1) -> list[dict]:
    pc = get_project_client(project_id)
    items = pc.get_work_items(query=f"updated:[NOW-{days}DAY TO NOW]")
    return [{"id": i.id, "title": i.title, "updated": i.updated} for i in items]
```

**Key files:**
- `.claude/scripts/integrations/polarion.py`
- Add to `query.py`: `query.py polarion open`, `query.py polarion changes`

**Dependencies:** Phase 1, Phase 8.
**Estimated complexity:** Medium

---

### 4d: Microsoft Teams (Later Priority)

**What to build:** Read Teams @mentions and messages relevant to Orsox's projects.

**Library:** `pip install msgraph-sdk azure-identity`

**Auth:** Azure Entra ID app registration → Device Code Flow (interactive login once, token cached in `~/.cache/teams-token`). For headless VPS: use Client Credentials with admin-consented app-level permissions.

**Required Azure permissions:** `Chat.Read`, `ChannelMessage.Read.All`, `User.Read`

**Setup steps:**
1. Azure Portal → Microsoft Entra ID → App registrations → New registration
2. Add API permissions (above) → Grant admin consent (required for `ChannelMessage.Read.All` in most orgs)
3. Save `client_id` and `tenant_id` to `.env`

```python
# integrations/teams.py
from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
import asyncio, os

def get_client():
    cred = DeviceCodeCredential(
        client_id=os.environ["AZURE_CLIENT_ID"],
        tenant_id=os.environ["AZURE_TENANT_ID"]
    )
    return GraphServiceClient(cred, scopes=["Chat.Read", "ChannelMessage.Read.All"])

async def get_unread_mentions() -> list[dict]:
    client = get_client()
    chats = await client.me.chats.get()
    # Filter for messages containing @Orsox within last 24h
    ...

def get_project_relevant_messages(messages: list[dict], project_keywords: list[str]) -> list[dict]:
    """Filter messages by project keywords from USER.md."""
    ...
```

**Key gotcha:** `ChannelMessage.Read.All` requires admin consent in corporate tenants — coordinate with IT admin before building this. For personal chats only, `Chat.Read` suffices and requires no admin.

**Key files:**
- `.claude/scripts/integrations/teams.py`
- Add to `query.py`: `query.py teams mentions`, `query.py teams unread`

**Dependencies:** Phase 1, Phase 8.
**Estimated complexity:** Medium-High (Azure admin coordination required)

---

### 4e: GitLab (Later Priority)

**What to build:** Monitor commits and MRs in Orsox's projects for coworker activity.

**Library:** `pip install python-gitlab`

**Auth:** Personal Access Token with `read_api` scope (GitLab → User Settings → Access Tokens).

```python
# integrations/gitlab.py
import gitlab, os, datetime

def get_client():
    return gitlab.Gitlab(url=os.environ["GITLAB_URL"],
                         private_token=os.environ["GITLAB_TOKEN"])

def get_recent_commits(project_path: str, days: int = 1) -> list[dict]:
    gl = get_client()
    project = gl.projects.get(project_path)
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat() + "Z"
    commits = project.commits.list(since=since, iterator=True)  # iterator=True avoids OOM on large repos
    return [{"id": c.id[:8], "author": c.author_name, "message": c.title, "time": c.created_at}
            for c in commits]

def get_open_mrs(project_path: str) -> list[dict]:
    gl = get_client()
    project = gl.projects.get(project_path)
    mrs = project.mergerequests.list(state="opened", iterator=True)
    return [{"iid": mr.iid, "title": mr.title, "author": mr.author["name"]} for mr in mrs]
```

**Rate limits:** GitLab.com: 2000 req/min authenticated. Always use `iterator=True` for list operations.

**Key files:**
- `.claude/scripts/integrations/gitlab.py`
- Add to `query.py`: `query.py gitlab commits`, `query.py gitlab mrs`

**Dependencies:** Phase 1, Phase 8.
**Estimated complexity:** Low-Medium

---

### 4f: OneDrive (Later Priority)

**What to build:** Surface recently modified project documents from OneDrive.

**Library:** `msgraph-sdk` (shared Azure auth with Teams)

**Required permissions:** `Files.Read`, `Files.Read.All`

```python
# integrations/onedrive.py
# Reuses Teams Azure auth setup
async def list_recent_files(days: int = 3) -> list[dict]:
    client = get_graph_client()  # same as teams.py
    # GET /me/drive/root/delta?$select=name,lastModifiedDateTime,webUrl
    result = await client.me.drive.root.delta.get()
    ...

async def search_files(query: str) -> list[dict]:
    client = get_graph_client()
    result = await client.me.drive.root.search_with_q(q=query).get()
    ...
```

**Key files:**
- `.claude/scripts/integrations/onedrive.py`
- Add to `query.py`: `query.py onedrive recent`, `query.py onedrive search "<query>"`

**Dependencies:** Phase 4d (shares Azure auth setup).
**Estimated complexity:** Low (once Azure auth is done)

---

## Phase 5: Skills (Starter Pack)

**What to build:** Two skills that give the agent structured knowledge about Orsox's vault and automate the top task (Jira triage).

### Skill 1: Vault Navigator

Teaches the agent Orsox's exact folder structure, naming conventions, and how to create/update notes.

```
.claude/skills/vault-navigator/
  SKILL.md                     ← trigger: "vault", "memory", "notes", "obsidian"
  references/
    vault-structure.md         ← folder map, naming conventions (meetings/YYYY-MM-DD_*.md, etc.)
```

**SKILL.md example:**
```yaml
---
name: vault-navigator
description: Knows Orsox's Obsidian vault structure and can create/find notes
triggers: [vault, memory, note, obsidian, drawio]
---
Use this skill when creating or locating vault files.
Meetings go in meetings/ as YYYY-MM-DD_<topic>.md.
Projects go in projects/<project-name>.md.
Team context goes in team-context/<person-name>.md.
All new notes start with # Title + date frontmatter.
```

### Skill 2: Jira Triage Assistant

Trigger: "triage jira", "new tickets". Fetches new Jira tickets, scores them, writes a triage draft.

```
.claude/skills/jira-triage/
  SKILL.md
  scripts/
    triage.py                  ← deterministic scorer (AI/agent keyword boosting)
  references/
    triage-rules.md            ← Orsox's triage criteria
```

**`triage.py` scorer logic:**
```python
AI_KEYWORDS = ["agent", "LLM", "AI", "model", "embedding", "vector", "RAG", "Claude"]

def score_ticket(ticket: dict) -> int:
    score = 0
    text = f"{ticket['summary']} {ticket.get('description','')}"
    # Boost AI/agent related tickets
    for kw in AI_KEYWORDS:
        if kw.lower() in text.lower():
            score += 2
    # Flag incomplete tickets
    if not ticket.get("description"):
        score -= 3
    # Priority boost
    if ticket["priority"] == "High":
        score += 3
    elif ticket["priority"] == "Critical":
        score += 5
    return score
```

**Draft output format** (`drafts/active/2026-05-17_jira-triage_<date>.md`):
```markdown
---
type: jira-triage
created: 2026-05-17T09:15:00+02:00
status: active
---
## Jira Triage — 2026-05-17

### High Priority (action needed)
- **AI-142** — [title] | Priority: High | AI-related: yes
  Suggested: assign to self, start today

### Needs Info
- **AI-143** — [title] | No description — ping requester
```

**Dependencies:** Phase 4b.
**Estimated complexity:** Low-Medium

---

## Phase 6: Proactive Systems (Heartbeat + Reflection)

**What to build:** The heartbeat script — the brain that ties everything together. Gathers data from all integrations, has Claude reason over it, surfaces actionable drafts and notifications.

### Heartbeat

**Orsox's Advisor-level behaviors:**
- Gathers: new Jira tickets, Teams @mentions, GitLab commits in Orsox's repos, Polarion work item changes
- Claude reasons over pre-loaded data → writes draft triage notes to `drafts/active/`
- Sends desktop notifications via `notify-send` — never auto-sends any message
- Habit tracking: **suggests** specific actions for unchecked HABITS.md pillars (does NOT auto-check — Advisor level)
- Late-day nudge at 17:30 CET if any pillars still unchecked

**Claude Agent SDK usage in heartbeat:**
```python
# heartbeat.py
from claude_agent_sdk import query, ClaudeAgentOptions
import asyncio, json, pathlib

SOUL = pathlib.Path.home() / "Memory/SOUL.md"

async def run_heartbeat():
    # 1. Python gathers all data (no Claude yet)
    context = build_context()  # calls jira.get_new_tickets(), gitlab.get_recent_commits(), etc.
    context = sanitize(context)  # Phase 8: sanitize before Claude sees it

    # 2. Claude reasons over pre-loaded context
    options = ClaudeAgentOptions(
        system_prompt=SOUL.read_text(),
        allowed_tools=[],  # read-only during heartbeat — no file writes by Claude
        permission_mode="default"
    )
    result_text = ""
    async for message in query(prompt=f"Heartbeat context:\n{context}", options=options):
        if message.type == "result":
            result_text = message.content

    # 3. Python writes the draft (not Claude)
    if result_text:
        write_draft(result_text)
        notify("Second Brain: Heartbeat complete — check drafts/active/")

asyncio.run(run_heartbeat())
```

**State diffing (only notify on changes):**
```python
# Load previous state
state_path = pathlib.Path(".claude/data/state/heartbeat-state.json")
prev = json.loads(state_path.read_text()) if state_path.exists() else {}
current = build_snapshot()  # dict of {jira: [issue_ids], gitlab: [commit_shas], ...}
diff = diff_snapshot(prev, current)
if diff:
    state_path.write_text(json.dumps(current))
    # Only proceed with Claude reasoning if something changed
```

**`Memory/HABITS.md` structure:**
```markdown
# Orsox's Daily Pillars

## Today — 2026-05-17
- [ ] AI Learning — Read 1 paper or complete 1 tutorial
- [ ] Agent Shipping — Commit working code to an AI agent project
- [ ] Team Awareness — Check in with 1 teammate
- [ ] Deep Work — 2+ uninterrupted hours on primary project
- [ ] Health — 30 min movement

## History
### 2026-05-16
- [x] AI Learning
- [x] Agent Shipping
- [ ] Team Awareness
...
```

**`Memory/HEARTBEAT.md` — Orsox's monitor checklist:**
```markdown
# Heartbeat Monitor Checklist

## Jira
- New tickets in my project keys (unassigned or assigned to me)
- Tickets I own that are overdue

## Teams
- @mentions in any channel
- DMs from teammates about my projects

## GitLab
- Commits to my project repos by coworkers (last 24h)
- Open MRs needing my review

## Polarion
- Work item status changes in my project IDs
- New requirements added

## Habits
- Late-day nudge if pillars unchecked by 17:30 CET
```

### Daily Reflection

**What to build:** A nightly script that promotes the day's important entries from the daily log to MEMORY.md — the "sleep consolidation" for the second brain.

```python
# memory_reflect.py — runs daily at 08:00 CET
# 1. Read yesterday's daily/YYYY-MM-DD.md
# 2. Claude Agent SDK: "Extract key decisions, architectural choices, and facts worth long-term retention"
# 3. Append promoted items to MEMORY.md (respecting the <3KB limit — prune oldest if needed)
```

**Key files:**
- `.claude/scripts/heartbeat.py`
- `.claude/scripts/memory_reflect.py`
- `.claude/data/state/heartbeat-state.json`
- `~/Memory/HEARTBEAT.md`
- `~/Memory/HABITS.md`

**Dependencies:** Phases 1–5.
**Estimated complexity:** High

**Personalization notes:**
- Heartbeat priority order mirrors Orsox's top tasks: (1) Jira triage, (2) Teams project relevance, (3) GitLab coworker activity, (4) Polarion changes, (5) Habit nudge.
- Meeting creation (top task #5) → heartbeat detects a meeting is needed (Jira task, Teams thread), drafts an agenda and invite text in `drafts/active/` — Orsox creates the actual calendar invite.
- Draft voice-matching: when generating Teams reply drafts, run `memory_search.py --path-prefix drafts/sent` to find similar past replies and match Orsox's tone.

---

## Phase 7: Chat Interface (Teams Bot)

**What to build:** A bot that accepts Teams DMs or @mentions and routes them to the Claude Agent SDK, enabling conversational access to the second brain from within Teams.

**Architecture:**
- Teams Bot Framework registration → FastAPI webhook endpoint (on VPS)
- Each Teams thread = persistent Agent SDK conversation (stored in `.claude/data/chat.db`)
- `TeamsAdapter` handles message parsing and reply posting via Graph API

**Key files:**
- `.claude/chat/server.py` — FastAPI app, handles `/webhook` POST from Teams
- `.claude/chat/adapters/teams.py` — `TeamsAdapter`: parse incoming → Agent SDK → post reply via Graph API
- `.claude/chat/session_store.py` — SQLite at `.claude/data/chat.db` (thread_id → conversation history)

**Security:** All incoming Teams messages pass through `sanitize.py` before reaching Claude. Replies are staged as drafts — Orsox reviews before they're posted (Advisor mode: even bot replies go to drafts first).

**Dependencies:** Phases 2, 4d, 8.
**Estimated complexity:** High

**Setup requirement:** Teams Bot Framework registration requires IT admin approval in most corporate tenants — plan for this coordination early.

---

## Phase 8: Security Hardening

**What to build:** Three-layer defense enforcing Orsox's security boundaries and sanitizing all external data before it reaches Claude.

**Orsox's guardrail rules:**

| Boundary | Rule |
|---|---|
| Send Teams messages | BLOCK — POST to Teams/chat APIs is forbidden |
| Post anywhere | BLOCK — no social, no comments, no issue updates |
| Files outside vault | BLOCK — writes only allowed inside `~/Memory/` |
| Financial APIs | BLOCK — any endpoint with payment/billing/financial in URL |
| Delete anything | BLOCK — `rm`, `DELETE` HTTP method, `unlink`, `shutil.rmtree` |

**Key files:**
- `.claude/scripts/sanitize.py` — 3-layer pipeline applied to all integration output:
  1. Pattern detection: regex for prompt injection (`ignore previous instructions`, `<system>`, etc.)
  2. Markdown escaping: escape backticks, asterisks that could alter formatting
  3. XML trust boundary: wrap in `<external-data trust="low">...</external-data>`
- `.claude/scripts/shared.py` — `check_guardrails(command: str) -> bool`: blocklist patterns + LLM eval for ambiguous cases
- `.claude/hooks/pre-tool-guardrail.py` — PreToolUse hook: intercepts all tool calls, checks against guardrails, exits with code 2 to block

**PreToolUse hook registration in `.claude/settings.json`:**
```json
"PreToolUse": [
  {
    "hooks": [
      { "type": "command", "command": "python3 .claude/hooks/pre-tool-guardrail.py" }
    ]
  }
]
```

**API key isolation:** All tokens live in `.env` (gitignored). Claude only ever sees formatted data strings — never raw API responses, never tokens, never PII beyond what's needed for context.

**`.env` template:**
```bash
# Jira
JIRA_URL=https://yourcompany.atlassian.net
JIRA_TOKEN=...
JIRA_EMAIL=orsox@yourcompany.com

# GitLab
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=...

# Polarion
POLARION_URL=https://polarion.yourcompany.com
POLARION_TOKEN=...

# Azure (Teams + OneDrive)
AZURE_CLIENT_ID=...
AZURE_TENANT_ID=...

# Database
DB_URL=postgresql://user:pass@vps-host:5432/second_brain
```

**Dependencies:** Phase 2 (hooks framework).
**Estimated complexity:** Medium

---

## Phase 9: Deployment (Linux + VPS)

**What to build:** Full deployment across Orsox's Linux desktop and VPS, with vault sync and systemd timers.

### Local (Linux)

**Python environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install atlassian-python-api python-gitlab polarion-rest-api-client \
            msgraph-sdk azure-identity fastembed claude-agent-sdk \
            fastapi uvicorn python-dotenv
```

**Systemd user timers** (`~/.config/systemd/user/`):

`heartbeat.service`:
```ini
[Unit]
Description=Orsox's Second Brain Heartbeat

[Service]
Type=oneshot
WorkingDirectory=/path/to/second-brain
ExecStart=/path/to/.venv/bin/python .claude/scripts/heartbeat.py
EnvironmentFile=/path/to/.env
```

`heartbeat.timer`:
```ini
[Unit]
Description=Run heartbeat every 30 min during work hours (Berlin)

[Timer]
OnCalendar=*-*-* 07..20:00/30:00
Persistent=true

[Install]
WantedBy=timers.target
```

`reflection.timer`:
```ini
[Timer]
OnCalendar=*-*-* 08:00:00
```

**Enable:**
```bash
systemctl --user enable --now heartbeat.timer reflection.timer memory-index.timer
```

### VPS (Linux)

**Database setup:**
```bash
apt install postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER secondbrain WITH PASSWORD 'secret';"
sudo -u postgres psql -c "CREATE DATABASE second_brain OWNER secondbrain;"
psql -U secondbrain second_brain -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**Vault sync (git-based):**
```bash
# On VPS: init bare repo
git init --bare ~/memory-sync.git

# On local: add remote
git -C ~/Memory remote add vps user@vps-ip:memory-sync.git

# git-sync service: pulls from local, pushes to VPS every 2 min
# .claude/deploy/git-sync.service — ExecStart=/usr/local/bin/git-sync --repo ~/Memory --remote vps
```

**Headless OAuth for Teams/OneDrive on VPS:**
```bash
# Run once locally (device code flow — opens browser):
python3 .claude/scripts/integrations/teams.py --auth
# Token cached at ~/.cache/teams-token.json
# Rsync to VPS:
rsync ~/.cache/teams-token.json vps-user@vps-ip:~/.cache/
```

**Cost estimate:**
| Item | Monthly |
|---|---|
| Claude Max | ~$100 |
| VPS (e.g., Hetzner CX21, 2 vCPU / 4GB RAM) | ~$5–8 |
| Obsidian sync (not needed — using git) | $0 |
| **Total** | **~$105–110/mo** |

**Key files:**
- `.claude/deploy/setup-local.sh`
- `.claude/deploy/setup-vps.sh`
- `.claude/deploy/heartbeat.service` + `heartbeat.timer`
- `.claude/deploy/reflection.service` + `reflection.timer`
- `.claude/deploy/memory-index.service` + `memory-index.timer`
- `.claude/deploy/git-sync.service`

**Dependencies:** All phases.
**Estimated complexity:** Medium (Linux/VPS setup is routine for a Mega-Power-Engineer)

---

## Recommended Build Order

Phases are mostly sequential; 8 can be developed in parallel with 4–6.

```
Phase 1 (Foundation)
    └── Phase 2 (Hooks)
            └── Phase 3 (RAG)   ← can start after Phase 1
            └── Phase 8 (Security) ← start after Phase 2
                    └── Phase 4a (Obsidian)
                    └── Phase 4b (Jira)
                    └── Phase 4c (Polarion)
                    └── Phase 4d (Teams) ← needs Azure admin
                    └── Phase 4e (GitLab)
                    └── Phase 4f (OneDrive) ← after 4d
                └── Phase 5 (Skills) ← after 4b
                └── Phase 6 (Heartbeat) ← after 4a–4c + 5
                └── Phase 7 (Teams Bot) ← after 4d + 6
Phase 9 (Deployment) ← after all phases, but start VPS Postgres in parallel with Phase 3
```

**Suggested sprint plan:**
- **Week 1:** Phases 1 + 2 (vault + hooks — immediate value in every session)
- **Week 2:** Phase 3 (RAG) + Phase 8 (security framework)
- **Week 3:** Phases 4a + 4b + 4c (Obsidian + Jira + Polarion)
- **Week 4:** Phase 5 (skills) + start Phase 6 (heartbeat)
- **Week 5:** Phase 6 completion + Phase 9 (VPS deployment)
- **Week 6+:** Phase 4d/e/f (Teams + GitLab + OneDrive) + Phase 7 (Teams bot)

---

*This PRD was generated from your requirements on 2026-05-17. Revisit and update as your system evolves — especially USER.md as your project list changes and HEARTBEAT.md as your monitoring needs shift.*
