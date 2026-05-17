# BorgOS Platform — Product Specification

---

## 1. Product Overview

### What It Is

BorgOS is a unified local-first platform application delivering three integrated modules — **Archon Hub**, **Second Brain**, and **Task Automation** — behind a single, immersive Borg-themed web GUI. It runs as a self-hosted FastAPI server accessed through any modern browser, with no cloud dependency.

### Who It's For

Power users, AI engineers, and knowledge workers who use the Archon agent framework and want a single operational dashboard for managing reusable AI assets, personal knowledge, and automated task execution. The target user is technically proficient, runs Archon locally, and values aesthetic cohesion and keyboard-accessible tooling.

### Core Value Proposition

- **One interface, three tools**: Archon asset management, a personal knowledge graph, and a cron-style task scheduler — unified under one application shell.
- **Borg aesthetic as functional design**: The visual language is not decorative; dark backgrounds, high-contrast cyan/green glows, and hexagonal motifs reinforce information hierarchy and focus.
- **Local-first, zero SaaS**: Runs entirely on the user's machine. SQLite by default; PostgreSQL-ready for multi-user deployments.
- **Deep Archon integration**: Module 1 and Module 3 are Archon-aware — they can read the local Archon installation directory and trigger workflows on schedule.

---

## 2. Tech Stack

### Backend

| Layer | Choice | Version |
|---|---|---|
| Runtime | Python | 3.12+ |
| Web framework | FastAPI | 0.115.x |
| ASGI server | Uvicorn with `uvicorn[standard]` | 0.30.x |
| ORM | SQLAlchemy (async) | 2.0.x |
| DB driver (SQLite) | `aiosqlite` | 0.20.x |
| DB driver (Postgres) | `asyncpg` | 0.29.x |
| Migrations | Alembic | 1.13.x |
| Scheduling engine | APScheduler (AsyncIOScheduler) | 3.10.x |
| Auth | `python-jose` (JWT) + `passlib[bcrypt]` | jose 3.3.x / passlib 1.7.x |
| Validation | Pydantic v2 | 2.7.x |
| File watching | `watchfiles` | 0.22.x |
| HTTP client | `httpx` | 0.27.x |
| Knowledge graph | `networkx` | 3.3.x |
| Settings | `pydantic-settings` | 2.3.x |
| Environment | `python-dotenv` | 1.0.x |

### Frontend

| Layer | Choice | Version |
|---|---|---|
| Framework | Svelte + SvelteKit | SvelteKit 2.x / Svelte 5.x |
| Build tool | Vite | 5.x |
| Type system | TypeScript | 5.x |
| CSS | Tailwind CSS v4 | 4.x |
| Component library | Custom Borg design system (no third-party component lib) | — |
| Icons | Lucide Svelte | 0.400.x |
| Graph visualization | `@xyflow/svelte` (React Flow port) | 0.1.x |
| HTTP client | Native `fetch` with typed wrappers | — |
| State management | Svelte stores (built-in) + Svelte 5 runes | — |
| Routing | SvelteKit file-based routing | — |
| Code editor (notes) | CodeMirror 6 | 6.x |
| Markdown rendering | `marked` + `DOMPurify` | marked 12.x / DOMPurify 3.x |
| Notifications | Custom Borg-styled toast system | — |
| Date/time picker | `flatpickr` (custom Borg theme) | 4.x |

### Database Schema Storage

- **Default**: SQLite at `~/.borgos/borgos.db`
- **Override**: `DATABASE_URL` env var accepts any SQLAlchemy-compatible URL
- Migrations managed by Alembic; auto-applied on startup in development mode

### Project Structure

```
borgos/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory
│   │   ├── config.py                # pydantic-settings config
│   │   ├── database.py              # async engine + session factory
│   │   ├── auth/
│   │   │   ├── router.py            # POST /api/auth/token, /api/auth/refresh
│   │   │   ├── models.py
│   │   │   └── service.py
│   │   ├── archon_hub/
│   │   │   ├── router.py            # /api/archon/*
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── scanner.py           # local Archon installation reader
│   │   ├── second_brain/
│   │   │   ├── router.py            # /api/brain/*
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── graph.py             # networkx graph operations
│   │   ├── task_automation/
│   │   │   ├── router.py            # /api/tasks/*
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── scheduler.py         # APScheduler integration
│   │   └── shared/
│   │       ├── exceptions.py
│   │       └── pagination.py
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app.html
│   │   ├── app.css                  # Tailwind base + Borg CSS vars
│   │   ├── lib/
│   │   │   ├── components/          # Shared Borg design system components
│   │   │   ├── stores/              # Svelte stores
│   │   │   ├── api/                 # Typed fetch wrappers
│   │   │   └── utils/
│   │   └── routes/
│   │       ├── +layout.svelte       # App shell with Borg nav
│   │       ├── +page.svelte         # Dashboard
│   │       ├── archon/
│   │       ├── brain/
│   │       └── tasks/
│   ├── static/
│   │   └── borg-hex-pattern.svg
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 3. Design Language

### Philosophy

The UI should feel like the interior of a Borg cube: functional, cold, relentless, and precise. Every element serves a purpose. Decoration is minimal but menacing. The grid is dominant. Glow effects are used sparingly to denote active states, not as ambient decoration.

### Color Palette

| Token | Hex | Usage |
|---|---|---|
| `--borg-black` | `#080b0d` | Page background, deepest surfaces |
| `--borg-void` | `#0d1117` | Card/panel backgrounds |
| `--borg-panel` | `#111820` | Elevated panels, modals |
| `--borg-grid` | `#161f2a` | Table rows, alternating backgrounds |
| `--borg-border` | `#1e3040` | Default borders and dividers |
| `--borg-border-active` | `#2a5068` | Focused/hovered borders |
| `--borg-cyan` | `#00e5ff` | Primary accent — active states, links, glows |
| `--borg-cyan-dim` | `#00b4cc` | Secondary cyan — hover states |
| `--borg-green` | `#39ff14` | Success, online status, assimilation complete |
| `--borg-green-dim` | `#2acc10` | Secondary green |
| `--borg-amber` | `#ffaa00` | Warning states |
| `--borg-red` | `#ff2244` | Error, critical, danger |
| `--borg-text-primary` | `#c8e6f0` | Primary readable text |
| `--borg-text-secondary` | `#6a9ab0` | Secondary/muted text |
| `--borg-text-disabled` | `#2a4a5e` | Disabled states |

### Glow Effects

```css
/* Active element glow */
--glow-cyan: 0 0 8px #00e5ff44, 0 0 20px #00e5ff22, 0 0 40px #00e5ff11;
--glow-green: 0 0 8px #39ff1444, 0 0 20px #39ff1422;
--glow-red:   0 0 8px #ff224444, 0 0 20px #ff224422;
```

Glows are applied via `box-shadow` or `text-shadow` and ONLY on `:focus`, `:active`, or explicitly `.state-active` elements. Never as ambient decoration on static elements.

### Typography

| Role | Font | Weight | Size |
|---|---|---|---|
| Display / Module headings | `Share Tech Mono` (Google Fonts) | 400 | 24–32px |
| Body / Labels | `JetBrains Mono` (Google Fonts) | 400 | 13–14px |
| Micro / Status text | `JetBrains Mono` | 400 | 11px |
| Numbers / Data | `JetBrains Mono` | 600 | inherit |

All fonts are monospace — no sans-serif or serif anywhere in the UI. This reinforces the cybernetic, terminal-like aesthetic.

### Hexagonal Pattern

A repeating SVG hexagonal grid (`borg-hex-pattern.svg`) with 1px `--borg-border` strokes at 4% opacity is used as a `background-image` overlay on the main page background and module header areas. The hex grid does not appear on content cards.

### Component Patterns

**Borg Panel** (`BorgPanel.svelte`): The primary card container. Flat background `--borg-void`, 1px solid `--borg-border`, no `border-radius` (all corners are sharp — Borg geometry is rectilinear), subtle inner-shadow on top edge.

**Borg Button** (`BorgButton.svelte`):
- Variants: `primary` (cyan fill), `secondary` (transparent + cyan border), `danger` (red border), `ghost` (no border)
- Shape: `border-radius: 0` — sharp corners everywhere
- Active state: glow effect + slight inset shadow
- Disabled: opacity 0.3, cursor not-allowed

**Borg Input** (`BorgInput.svelte`):
- Background: `--borg-void`
- Border: `1px solid --borg-border`
- Focus: border changes to `--borg-cyan`, `--glow-cyan` box-shadow
- Text: `--borg-text-primary`, monospace

**Borg Badge** (`BorgBadge.svelte`):
- Status indicators: `online` (green), `idle` (amber), `error` (red), `assimilated` (cyan)
- Hexagonal clip-path shape for visual consistency

**Borg Table** (`BorgTable.svelte`):
- Alternating row colors: `--borg-void` / `--borg-grid`
- Header row: `--borg-panel` with top-border `--borg-cyan` 2px
- Row hover: `--borg-border-active` background tint

**HexLoader** (`HexLoader.svelte`):
- Animated SVG of 7 hexagons pulsing in sequence in `--borg-cyan`
- Used as the global loading state indicator

**BorgNav** (`BorgNav.svelte`):
- Fixed left sidebar, 220px wide
- Top: BorgOS logo (pixelated Borg cube SVG)
- Navigation items with `--borg-cyan` left-border indicator on active route
- Module sections separated by faint `--borg-border` dividers
- Bottom: user info + logout

### Spacing System

Base unit: `4px`. All spacing is multiples of 4: `4, 8, 12, 16, 24, 32, 48, 64`. Tailwind's default scale is overridden in `tailwind.config.ts` to enforce this.

### Animation Principles

- Transitions: `150ms ease-out` for hover states, `200ms ease-in-out` for panel open/close
- No bounce, spring, or playful easing — all motion is linear or ease
- Scan-line animation: a subtle 1px horizontal scan line sweeping top-to-bottom on module headers every 4 seconds at 3% opacity
- Text that represents live status values uses a 1-second CSS flicker on first render

---

## 4. Feature List

### Module 0: Application Shell (Shared)

**P0 — Must Have**
- F0.1: JWT-based authentication with `/login` page (token stored in `httpOnly` cookie)
- F0.2: Persistent left sidebar navigation with module icons and labels
- F0.3: Global notification/toast system with Borg-styled alerts
- F0.4: Dark mode enforced globally — no light mode toggle
- F0.5: Hexagonal background pattern rendered as SVG overlay on layout
- F0.6: Responsive layout (works at 1280px–2560px; minimum 1024px supported)
- F0.7: Global HexLoader overlay for async navigation transitions
- F0.8: `/health` endpoint on backend returning uptime and module status
- F0.9: Top status bar showing: current time (UTC), DB connection status, scheduler status

**P1 — Should Have**
- F0.10: Keyboard shortcut system (e.g., `G+H` → Hub, `G+B` → Brain, `G+T` → Tasks)
- F0.11: Settings page: Archon installation path, DB path, JWT secret rotation
- F0.12: `/api/status` endpoint returning all module health details as JSON

---

### Module 1: Archon Hub

**P0 — Must Have**
- F1.1: Scan configured Archon installation directory and index all YAML/JSON workflow, skill, and agent definitions
- F1.2: Paginated asset browser with type filter (Workflows / Skills / Agents) and full-text search
- F1.3: Asset detail view: name, description, version, dependencies, raw YAML/JSON viewer
- F1.4: "Copy to System" button — copies the selected asset file to the local Archon installation path
- F1.5: Asset tags extracted from YAML frontmatter, rendered as Borg badges
- F1.6: Last-scanned timestamp displayed in module header; manual "Re-scan" trigger button
- F1.7: Asset card grid view with hex-badge showing asset type
- F1.8: Persistent SQLite storage of indexed assets (so page loads don't require a re-scan)

**P1 — Should Have**
- F1.9: File watcher: auto re-index when Archon installation directory changes (`watchfiles`)
- F1.10: Asset dependency graph — visual node graph showing which skills a workflow uses
- F1.11: Copy history log showing last 50 copy-to-system operations with timestamps
- F1.12: "Mark as Favorite" functionality with favorites filter view
- F1.13: Bulk copy — select multiple assets and copy all in one action
- F1.14: Asset version diffing — show changes between two versions of the same asset name

**P2 — Nice to Have**
- F1.15: Export selected assets as a `.zip` archive
- F1.16: Import assets from a `.zip` archive into the Archon Hub store
- F1.17: Preview: render Markdown documentation embedded in YAML descriptions

---

### Module 2: Second Brain

**P0 — Must Have**
- F2.1: Create, read, update, delete notes with a CodeMirror 6 Markdown editor
- F2.2: Note list sidebar with search and creation date sort
- F2.3: Rendered Markdown preview mode (toggle between edit and preview)
- F2.4: Full-text search across all notes with highlighted match snippets
- F2.5: Tags on notes (comma-separated input, stored as array in DB)
- F2.6: Manual link creation between notes: `[[Note Title]]` wiki-link syntax, stored as graph edges
- F2.7: Knowledge graph visualization using `@xyflow/svelte`: nodes = notes, edges = links
- F2.8: Click a node in the graph to navigate to that note
- F2.9: Graph view: color-code nodes by tag (using Borg accent colors)

**P1 — Should Have**
- F2.10: Backlinks panel on each note showing which other notes link to it
- F2.11: Auto-suggest related notes based on shared tags during editing
- F2.12: Note templates: pre-defined templates (daily log, idea capture, meeting note)
- F2.13: Archive notes (soft-delete with restore capability)
- F2.14: Export a note as Markdown `.md` file
- F2.15: Import `.md` files into Second Brain
- F2.16: Graph zoom to fit, zoom to selected node controls

**P2 — Nice to Have**
- F2.17: AI-assisted note linking: suggest connections based on content similarity
- F2.18: Daily note auto-creation at midnight via Task Automation integration
- F2.19: Pinned notes section at top of note list
- F2.20: Note word count and reading time estimate in status bar

---

### Module 3: Task Automation

**P0 — Must Have**
- F3.1: Create scheduled tasks with: name, description, schedule (cron expression or interval), command/script to run, enabled/disabled toggle
- F3.2: Cron expression builder UI (visual builder that generates cron strings)
- F3.3: Task list with current status (active/paused/error), next run time, last run time
- F3.4: Task execution history log: per-task paginated log of all past runs with timestamp, duration, exit code, stdout/stderr capture
- F3.5: Manual "Run Now" trigger for any task
- F3.6: Enable/disable tasks without deleting them
- F3.7: APScheduler integration running as a background service within the FastAPI process
- F3.8: Task types: `shell` (run a shell command), `archon_workflow` (trigger an Archon workflow by name)
- F3.9: Real-time task status updates via Server-Sent Events (SSE) on `GET /api/tasks/stream`

**P1 — Should Have**
- F3.10: Task run notifications: on-screen toast when a task completes or fails
- F3.11: Task run time statistics: average duration, success rate over last 30 days
- F3.12: Retry configuration: max retries on failure, retry delay
- F3.13: Task tags/categories for grouping related tasks
- F3.14: Pause all tasks globally (maintenance mode toggle)
- F3.15: Execution log search/filter by task name, status, date range

**P2 — Nice to Have**
- F3.16: Task dependency chains: task B runs only after task A succeeds
- F3.17: Webhook trigger: tasks that fire on `POST /api/tasks/{id}/trigger` with an API key
- F3.18: Task import/export as JSON
- F3.19: Email notification on task failure (SMTP config optional)

---

## 5. Sprint Plan

### Sprint 1: Foundation (Weeks 1–2)

**Goal**: Runnable application skeleton, auth, database, and Borg design system in place.

**Backend Deliverables**
- Project scaffold: `pyproject.toml` with all dependencies, `Makefile` with `dev`, `migrate`, `test` targets
- `config.py`: pydantic-settings loading `.env` for `DATABASE_URL`, `SECRET_KEY`, `ARCHON_PATH`, `CORS_ORIGINS`
- `database.py`: async SQLAlchemy engine, `get_session` dependency
- Alembic setup with initial migration for `users` table
- Auth module: `POST /api/auth/token` (login), `POST /api/auth/refresh`, `GET /api/auth/me`
- User model: `id`, `username`, `hashed_password`, `created_at`
- Default admin user seeded on first startup (username: `borg`, password from env `INITIAL_PASSWORD`)
- `GET /api/health` returning `{"status": "nominal", "uptime_seconds": N, "modules": {...}}`
- CORS middleware configured for `http://localhost:5173`
- Global exception handler returning `{"error": "message", "code": "BORG_ERROR_CODE"}` shape

**Frontend Deliverables**
- SvelteKit project initialized with TypeScript, Tailwind CSS v4, Vite
- `app.css`: all `--borg-*` CSS variables defined, `Share Tech Mono` and `JetBrains Mono` loaded from Google Fonts
- Tailwind config: spacing scale to 4px base, colors mapped to CSS vars
- `borg-hex-pattern.svg`: generated hexagonal tile SVG
- `+layout.svelte`: BorgNav sidebar + main content area, hex pattern background
- `BorgPanel`, `BorgButton`, `BorgInput`, `BorgBadge`, `HexLoader`, `BorgTable` components built and tested in isolation
- `/login` page: username/password form, JWT stored in `httpOnly` cookie via `Set-Cookie` header on backend
- Auth store: reactive `currentUser` derived from `/api/auth/me`
- Route guards: unauthenticated users redirected to `/login`
- Global toast store + `BorgToast` component (positioned top-right)
- Top status bar component: UTC clock, DB status dot, scheduler status dot

**Acceptance Criteria**
- `make dev` starts both backend (port 8000) and frontend (port 5173)
- Login flow works end-to-end
- All design system components render correctly with Borg aesthetic
- `/api/health` returns 200 with correct shape

---

### Sprint 2: Archon Hub (Weeks 3–4)

**Goal**: Module 1 fully functional — scan, browse, copy assets.

**Backend Deliverables**
- Alembic migration: `archon_assets` table (`id`, `name`, `type`, `description`, `tags`, `file_path`, `raw_content`, `last_scanned`, `is_favorite`, `created_at`)
- `archon_hub/scanner.py`: recursive directory walk of `ARCHON_PATH`, parse `.yaml`/`.json` files, extract `name`, `description`, `type`, `tags` from content
- `POST /api/archon/scan`: trigger manual re-scan, returns count of assets indexed
- `GET /api/archon/assets`: paginated list with `?type=`, `?search=`, `?tags=`, `?favorites=true` query params
- `GET /api/archon/assets/{id}`: full asset detail including raw file content
- `POST /api/archon/assets/{id}/copy`: copy asset file to Archon installation path, log to `copy_history` table
- `GET /api/archon/copy-history`: last 50 copy operations
- `POST /api/archon/assets/{id}/favorite`: toggle favorite status
- `watchfiles` integration: background task watching `ARCHON_PATH` and triggering re-scan on change

**Frontend Deliverables**
- `/archon` route: module dashboard with scan status, asset counts by type, last-scanned time
- Asset browser: filter tabs (All / Workflows / Skills / Agents), search input, paginated grid
- Asset card: hex-badge for type, name, description truncated to 2 lines, tags, favorite star, "Copy" button
- Asset detail slide-over panel: full description, tags, raw YAML/JSON rendered in CodeMirror (read-only, Borg dark theme)
- Copy-to-system confirmation modal with destination path shown
- "Re-scan" button with HexLoader animation during scan
- Copy history drawer showing last 50 operations
- Favorites filter toggle

**Acceptance Criteria**
- Pointing `ARCHON_PATH` at a directory with YAML files results in indexed assets visible in UI
- Copy to system places the file in the target directory
- File watcher triggers re-index within 2 seconds of a file change

---

### Sprint 3: Second Brain (Weeks 5–6)

**Goal**: Module 2 fully functional — note CRUD, wiki-links, knowledge graph.

**Backend Deliverables**
- Alembic migration: `notes` table (`id`, `title`, `content`, `tags`, `is_archived`, `created_at`, `updated_at`), `note_links` table (`source_id`, `target_id`)
- `POST /api/brain/notes`: create note
- `GET /api/brain/notes`: paginated list with `?search=`, `?tags=`, `?archived=false`
- `GET /api/brain/notes/{id}`: single note with backlinks
- `PUT /api/brain/notes/{id}`: update note content/title/tags
- `DELETE /api/brain/notes/{id}`: soft-delete (set `is_archived=true`)
- `GET /api/brain/notes/{id}/backlinks`: list of notes that link to this note
- `GET /api/brain/graph`: return all notes and links as `{"nodes": [...], "edges": [...]}` for graph rendering
- `second_brain/graph.py`: parse `[[Title]]` links from note content, upsert `note_links` rows on note save
- Full-text search using SQLite FTS5 virtual table over `notes.title` + `notes.content`

**Frontend Deliverables**
- `/brain` route: two-panel layout — note list sidebar (left), editor/preview (right)
- Note list: search input, tag filter chips, "New Note" button, sorted by `updated_at` desc
- CodeMirror 6 editor: Borg dark theme, `[[` triggers autocomplete for note titles, Markdown syntax highlighting
- Preview toggle: renders Markdown via `marked` with `DOMPurify` sanitization
- Tags input: comma-separated with tag badge rendering
- Backlinks panel: collapsible section at bottom of note showing inbound links
- `/brain/graph` route: full-page `@xyflow/svelte` knowledge graph with Borg node styling (dark nodes, cyan edges, green active node), click-to-navigate
- Graph controls: zoom-to-fit button, node count display
- Archive and restore actions on note context menu

**Acceptance Criteria**
- Creating a note with `[[Another Note]]` creates a graph edge visible in the graph view
- Full-text search returns results with highlighted snippets
- Graph renders all notes as nodes with correct edges

---

### Sprint 4: Task Automation (Weeks 7–8)

**Goal**: Module 3 fully functional — scheduling, execution, history, SSE.

**Backend Deliverables**
- Alembic migration: `tasks` table (`id`, `name`, `description`, `task_type` enum, `schedule`, `command`, `archon_workflow_name`, `is_enabled`, `tags`, `retry_max`, `retry_delay`, `created_at`, `updated_at`), `task_runs` table (`id`, `task_id`, `started_at`, `finished_at`, `status` enum, `exit_code`, `stdout`, `stderr`, `duration_ms`)
- `task_automation/scheduler.py`: APScheduler `AsyncIOScheduler`, startup/shutdown lifecycle hooks on FastAPI app, dynamic job registration/removal mirroring DB state
- `POST /api/tasks`: create task + register with scheduler
- `GET /api/tasks`: list with `?status=`, `?tags=`, `?search=`
- `GET /api/tasks/{id}`: task detail
- `PUT /api/tasks/{id}`: update task + reschedule
- `DELETE /api/tasks/{id}`: delete task + remove from scheduler
- `POST /api/tasks/{id}/toggle`: enable/disable task
- `POST /api/tasks/{id}/run`: immediate manual trigger, returns `task_run_id`
- `GET /api/tasks/{id}/runs`: paginated execution history
- `GET /api/tasks/stream` (SSE): emits `task_run_started`, `task_run_completed`, `task_run_failed` events
- Shell task executor: subprocess with timeout (default 300s), stdout/stderr captured to DB
- Archon workflow task executor: calls Archon's CLI or API to trigger a named workflow

**Frontend Deliverables**
- `/tasks` route: task list with status badges (active/paused/error), next-run countdown, last-run status
- Create/edit task form: name, description, type selector (Shell / Archon Workflow), schedule builder, command input or workflow selector
- Visual cron builder: select-based UI for minute/hour/day/month/weekday generating a cron string, with human-readable description ("Every day at 09:00 UTC")
- "Run Now" button with confirmation
- Enable/disable toggle switch (Borg-styled)
- Task detail drawer: config tab + run history tab
- Run history table: timestamp, duration, status badge, expandable stdout/stderr viewer (Borg terminal styling — black background, green text)
- SSE subscription: toast notification on task completion/failure, live status dot updates without polling

**Acceptance Criteria**
- Creating a task with a cron expression causes it to run at the scheduled time
- Manual "Run Now" captures stdout/stderr and displays in history within 2 seconds
- SSE stream delivers events to browser without polling

---

### Sprint 5: Integration, Polish & Hardening (Weeks 9–10)

**Goal**: Cross-module integrations, settings, performance, and production-readiness.

**Backend Deliverables**
- `GET /api/status`: combined health of all three modules (asset count, note count, active task count, next scheduled run)
- Settings API: `GET /api/settings`, `PUT /api/settings` for `archon_path`, `scanner_auto_watch`, `default_task_timeout`, `scheduler_timezone`
- JWT secret rotation endpoint: `POST /api/auth/rotate-secret` (invalidates all existing tokens)
- Rate limiting on auth endpoints using `slowapi` (10 req/min on `/api/auth/token`)
- Structured logging via `structlog` with JSON output, log level from env
- `docker-compose.yml` with `borgos-backend` and `borgos-frontend` services
- `Dockerfile` for backend (multi-stage, Python 3.12 slim)
- `Dockerfile` for frontend (build stage → nginx static serve)
- OpenAPI docs served at `/api/docs` (Swagger UI with Borg dark theme override)

**Frontend Deliverables**
- Dashboard `/` route: unified status panel showing counts from all three modules, next scheduled task, recently modified notes, recently copied assets
- Settings page `/settings`: form for all configurable settings, save with optimistic update
- Keyboard shortcut overlay: `?` key shows modal listing all shortcuts
- Second Brain → Task Automation integration: "Create Daily Note Task" preset in task creation form (auto-populates cron `0 0 * * *`, command creates today's note via API)
- Error boundary components: graceful degradation if a module's API is down
- Mobile-aware layout: hamburger nav at <1024px (sidebar collapses)
- Accessibility: all interactive elements have `aria-label`, focus rings use `--borg-cyan` outline
- Performance: SvelteKit route-level code splitting, asset grid virtualisation for lists >100 items

**Acceptance Criteria**
- Dashboard loads with accurate counts from all three modules
- `docker-compose up` brings up a fully functional application
- Lighthouse performance score ≥ 85 on dashboard route
- All P0 features pass manual smoke test end-to-end

---

### Sprint 6: Testing & Documentation (Week 11)

**Goal**: Confidence through test coverage; project is hand-off ready.

**Backend Deliverables**
- `pytest` + `pytest-asyncio` test suite
- Unit tests for: scanner YAML parsing, cron validation, wiki-link parser, copy-to-system path resolution
- Integration tests for all API routes using `httpx.AsyncClient` with test SQLite DB
- Auth tests: valid login, invalid credentials, expired token, token refresh
- Target: ≥ 80% line coverage on service and router layers

**Frontend Deliverables**
- Svelte component tests using `@testing-library/svelte` + `vitest`
- Tests for: BorgButton states, BorgInput validation, cron builder output, wiki-link autocomplete trigger
- E2E tests using Playwright: login flow, create note + create link + view in graph, create task + run now + view history

**Documentation Deliverables**
- `README.md`: prerequisites, quickstart with `make dev`, environment variable reference table
- `.env.example` with all variables documented inline
- API documented via FastAPI's auto-generated OpenAPI schema (all routes have `summary` and `description`)

**Acceptance Criteria**
- `pytest` passes with ≥ 80% coverage, no skipped tests
- Playwright E2E suite passes in headless mode
- `README.md` enables a new developer to run the project from scratch in under 10 minutes

---

## API Reference Summary

| Method | Path | Module | Description |
|---|---|---|---|
| POST | `/api/auth/token` | Auth | Login, returns JWT |
| POST | `/api/auth/refresh` | Auth | Refresh JWT |
| GET | `/api/auth/me` | Auth | Current user |
| GET | `/api/health` | Core | Service health |
| GET | `/api/status` | Core | All-module status |
| GET | `/api/settings` | Core | Read settings |
| PUT | `/api/settings` | Core | Update settings |
| POST | `/api/archon/scan` | Hub | Trigger asset scan |
| GET | `/api/archon/assets` | Hub | List assets |
| GET | `/api/archon/assets/{id}` | Hub | Asset detail |
| POST | `/api/archon/assets/{id}/copy` | Hub | Copy to system |
| POST | `/api/archon/assets/{id}/favorite` | Hub | Toggle favorite |
| GET | `/api/archon/copy-history` | Hub | Copy log |
| POST | `/api/brain/notes` | Brain | Create note |
| GET | `/api/brain/notes` | Brain | List notes |
| GET | `/api/brain/notes/{id}` | Brain | Note detail |
| PUT | `/api/brain/notes/{id}` | Brain | Update note |
| DELETE | `/api/brain/notes/{id}` | Brain | Archive note |
| GET | `/api/brain/notes/{id}/backlinks` | Brain | Backlinks |
| GET | `/api/brain/graph` | Brain | Graph data |
| POST | `/api/tasks` | Tasks | Create task |
| GET | `/api/tasks` | Tasks | List tasks |
| GET | `/api/tasks/{id}` | Tasks | Task detail |
| PUT | `/api/tasks/{id}` | Tasks | Update task |
| DELETE | `/api/tasks/{id}` | Tasks | Delete task |
| POST | `/api/tasks/{id}/toggle` | Tasks | Enable/disable |
| POST | `/api/tasks/{id}/run` | Tasks | Manual trigger |
| GET | `/api/tasks/{id}/runs` | Tasks | Run history |
| GET | `/api/tasks/stream` | Tasks | SSE event stream |
