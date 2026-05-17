---
name: vault-navigator
description: |
  Knows Orsox's Obsidian vault structure, naming conventions, and how to create or find notes.
  Use when: creating a new note, finding where something is stored, logging a meeting, starting a
  project file, updating team context, or any time you need to read from or write to ~/Memory/.
  Triggers: "create a note", "add to vault", "log this meeting", "new project note", "where is",
  "find my note about", "save this to memory", "update team context", "note about", "obsidian",
  "vault", "meeting notes", "project file".
argument-hint: "[note type or topic]"
---

# Vault Navigator

Orsox's Memory vault lives at `~/Memory/`. It is plain Markdown — Obsidian is just the viewer.
Load `references/vault-structure.md` for the full folder map and naming rules.

## Quick Reference

| What you're creating | Folder | Filename pattern |
|---|---|---|
| Meeting notes | `~/Memory/meetings/` | `YYYY-MM-DD_<topic-slug>.md` |
| Project status | `~/Memory/projects/` | `<project-slug>.md` |
| Team member profile | `~/Memory/team-context/` | `<firstname-lastname>.md` |
| Daily log entry | `~/Memory/daily/` | `YYYY-MM-DD.md` (append only) |
| Draft for review | `~/Memory/drafts/active/` | `YYYY-MM-DD_<type>_<slug>.md` |

## Rules

1. **Always use the correct folder.** Do not put notes in the vault root.
2. **Append to the daily log** — never edit past entries, only add new ones below.
3. **Only write inside `~/Memory/`.** Never touch files outside this path.
4. **Keep MEMORY.md under 3KB** — when adding to it, prune the oldest "In Progress" entries.
5. **Dates use Berlin time** (CET = UTC+1, CEST = UTC+2).

## Creating a Meeting Note

```markdown
# <Topic> — YYYY-MM-DD

**Attendees:** [names]
**Outcome:** [one sentence decision or conclusion]

## Discussion
[key points]

## Decisions
- [decision 1]

## Action Items
- [ ] [who]: [what] by [when]
```

Save as `~/Memory/meetings/YYYY-MM-DD_<topic-slug>.md`.
Then append a reference line to today's daily log.

## Creating a Project Note

```markdown
# <Project Name>

**Status:** [Active / On Hold / Done]
**Last updated:** YYYY-MM-DD
**Jira project:** [KEY]
**GitLab repo:** [namespace/repo]

## Goal
[one sentence]

## Current Focus
[what's happening right now]

## Key Decisions
- YYYY-MM-DD — [decision]

## Next Actions
- [ ] [what]
```

Save as `~/Memory/projects/<project-slug>.md`.

## Searching the Vault

For semantic search, use the RAG pipeline:
```bash
~/.local/bin/msearch "<query>"
```

For filename search:
```bash
~/.local/bin/q obsidian search "<query>"
```

For recent activity:
```bash
~/.local/bin/q obsidian recent --days 7
```
