---
name: jira-triage
description: |
  Fetch new Jira tickets, score by AI/agent relevance and priority, write a triage draft for
  Orsox's review. Never posts to Jira — drafts only.
  Use when: "triage jira", "triage tickets", "new tickets", "what's in jira", "jira backlog",
  "check jira", "what do I need to work on", "jira triage", "any new tickets".
argument-hint: "[--days N] [--projects KEY1,KEY2]"
---

# Jira Triage Skill

Scores and categorizes new Jira tickets by AI-relevance and priority. Writes a review draft to
`~/Memory/drafts/active/` — Orsox decides what to act on. Nothing is posted to Jira.

## Integration Status

!`~/.claude/venv/bin/python3 /home/bernd/Workbench/borg/.claude/scripts/query.py status 2>&1 | grep jira`

## Steps

### 1. Run the triage script

```bash
~/.claude/venv/bin/python3 /home/bernd/Workbench/borg/.claude/skills/jira-triage/scripts/triage.py
```

Optional flags:
- `--days 5` — look back 5 days (default: 3)
- `--projects AI,PLT` — override project keys from USER.md
- `--dry-run` — print scored list, skip writing the draft

### 2. Read and present the draft

After the script runs, read the draft it created:
```bash
cat ~/Memory/drafts/active/$(date +%Y-%m-%d)_jira-triage.md
```

Then present the **Action Now** and **Assign to Self** sections to Orsox. Skip Monitor unless asked.

### 3. Offer next actions (Advisor mode — suggest only)

For each "Action Now" ticket, suggest one of:
- "Assign this to yourself in Jira" (Orsox does it)
- "Add to your project note in the vault"
- "Draft a comment asking for clarification"

For "Needs Info" tickets, offer to draft a comment. Write it to
`~/Memory/drafts/active/YYYY-MM-DD_jira-comment_<KEY>.md` — never post it.

## If Jira Is Not Configured

If the script exits with "Jira not configured":
1. Tell Orsox to copy `.env.example` to `.env` and fill in `JIRA_URL` and `JIRA_TOKEN`
2. For Jira Server/DC: use a Personal Access Token (PAT)
3. For Jira Cloud: use an API Token and also set `JIRA_EMAIL=you@company.com` and `JIRA_CLOUD=true`

## If Tickets Were Provided Manually

If Orsox pastes ticket titles or descriptions directly, apply the triage rules from
`references/triage-rules.md` manually and produce the same categorized output.

## Triage Rules Reference

Load `references/triage-rules.md` for full scoring weights and category definitions.
Short version:
- Critical/Blocker → Action Now
- AI keyword hits (agent, LLM, model, embedding…) → Assign to Self
- No description → Needs Info
- Everything else → Monitor
