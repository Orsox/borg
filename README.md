# BorgOS Platform

> **Resistance is futile.**

A unified local-first platform delivering three integrated modules — **Archon Hub**, **Second Brain**, and **Task Automation** — behind a single, immersive Borg-themed web GUI.

## Architecture

```
borgos/
├── backend/              # FastAPI + SQLAlchemy (async)
│   ├── app/
│   │   ├── main.py       # App factory
│   │   ├── config.py     # Settings (pydantic-settings)
│   │   ├── database.py   # Async engine + session
│   │   ├── auth/         # JWT authentication
│   │   ├── archon_hub/   # Module 1: Archon asset management
│   │   ├── second_brain/ # Module 2: Knowledge graph & notes
│   │   └── task_automation/ # Module 3: Scheduled task execution
├── frontend/             # SvelteKit + Tailwind CSS
│   └── src/
│       ├── lib/          # Shared components (Borg design system)
│       └── routes/       # Page routes
└── thoughts/             # Project documentation
```

## Modules

### Module 1 — Archon Hub
Central repository for Archon Workflows, Skills, and Agents. Browse, search, and deploy assets to your local Archon installation.

### Module 2 — Second Brain
Personal knowledge management with wiki-links (`[[Note Title]]`), full-text search, and a visual knowledge graph.

### Module 3 — Task Automation
Schedule tasks with cron expressions, execute shell commands or Archon workflows, and monitor execution history via SSE.

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Node.js 18+

### Setup

```bash
# Install dependencies
make install

# Start development servers
# Backend on port 8000, Frontend on port 5173
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
cd frontend && npm run dev
```

### Default Credentials
- **Username:** `borg`
- **Password:** `borgborg` (configurable via `INITIAL_PASSWORD` env var)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./borgos.db` | Database connection string |
| `SECRET_KEY` | `change-me-in-production` | JWT signing secret |
| `INITIAL_PASSWORD` | `borgborg` | Default admin password |
| `ARCHON_PATH` | `/opt/archon` | Path to Archon installation |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed CORS origins (comma-separated) |

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/api/docs
- **ReDoc:** http://localhost:8000/api/redoc

## Design System

The BorgOS UI uses a custom design system inspired by the Borg from Star Trek: Enterprise:

- **Colors:** Dark backgrounds (#080b0d) with cyan (#00e5ff) and green (#39ff14) accents
- **Typography:** Share Tech Mono (headings) + JetBrains Mono (body)
- **Components:** BorgPanel, BorgButton, BorgInput, BorgBadge, HexLoader, BorgTable
- **Pattern:** Hexagonal grid overlay at 4% opacity

## Tech Stack

### Backend
- **FastAPI** 0.115 — Async web framework
- **SQLAlchemy** 2.0 — Async ORM
- **SQLite** (default) / **PostgreSQL** (via env var)
- **APScheduler** 3.10 — Task scheduling
- **python-jose** — JWT authentication

### Frontend
- **SvelteKit** 2.x — Full-stack framework
- **Svelte** 5.x — Reactive UI with runes
- **Tailwind CSS** 4.x — Utility-first styling
- **Lucide Svelte** — Icon library

## Development

```bash
# Run tests
cd backend && uv run pytest -v

# Database migrations
cd backend && uv run alembic upgrade head
```

## License

MIT
