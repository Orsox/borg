# Vault Structure Reference

Vault root: `~/Memory/`

```
Memory/
  SOUL.md           ← Agent identity, rules, hard limits (read-only reference)
  USER.md           ← Orsox's profile, integration config (update as details change)
  MEMORY.md         ← Working memory, loaded every session — keep under 3KB
  HABITS.md         ← Daily 5 pillars — heartbeat manages the checklist
  HEARTBEAT.md      ← What the heartbeat monitors — edit to add/remove watches

  daily/
    YYYY-MM-DD.md   ← Append-only timestamped log — everything goes here first

  meetings/
    YYYY-MM-DD_<topic>.md   ← One file per meeting

  projects/
    <project-slug>.md       ← One file per active project

  team-context/
    <firstname-lastname>.md ← One file per teammate

  drafts/
    active/
      YYYY-MM-DD_<type>_<slug>.md   ← Heartbeat drafts awaiting Orsox's review
    sent/
      YYYY-MM-DD_<type>_<slug>.md   ← Confirmed/used drafts (voice matching archive)
    expired/
      YYYY-MM-DD_<type>_<slug>.md   ← Auto-archived after 24h with no action
```

## Naming Rules

- **Slugs** are lowercase, hyphens only: `ai-agent-kickoff`, not `AI Agent Kickoff`
- **Dates** use YYYY-MM-DD format, Berlin timezone
- **Meeting files**: `2026-05-17_agent-platform-kickoff.md`
- **Draft files**: `2026-05-17_jira-triage_sprint-42.md`, `2026-05-17_teams-reply_alice.md`
- **Project files**: `agent-platform.md`, `llm-eval-suite.md`
- **Team files**: `alice-smith.md`, `bob-jones.md`

## MEMORY.md — Key Sections

```markdown
## Active Projects
## Key Decisions
## Important Facts
## Team
## Lessons Learned
## In Progress (This Week)
```

Prune "In Progress" weekly. Max file size: 3KB.

## Draft Frontmatter Format

All draft files must have this frontmatter:

```yaml
---
type: jira-triage | teams-reply | gitlab-mr | meeting-plan | general
source_id: <ticket-key or message-id or "">
recipient: <name or "">
subject: <topic>
created: YYYY-MM-DDTHH:MM:SS+02:00
status: active | sent | expired
---
```
