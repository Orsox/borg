# Jira Triage Rules — Orsox

## Scoring Weights

| Signal | Score |
|---|---|
| Priority: Critical / Blocker | +10 |
| Priority: High | +5 |
| Priority: Medium | +2 |
| AI/agent keyword in title or description | +2 per keyword (capped at 3) |
| Unassigned | +3 (needs someone to own it) |
| No description | -2 (incomplete, needs info before work) |

## AI-Relevant Keywords
agent, LLM, AI, model, embedding, vector, RAG, Claude, GPT, prompt, inference,
fine-tuning, neural, transformer, pipeline

Tickets with 2+ AI keywords → "Assign to Self" category minimum.
Tickets with 4+ AI keywords + High priority → "Action Now".

## Categories

### Action Now
- Critical or Blocker regardless of topic
- High priority + unassigned
- High priority + 3+ AI keywords

### Assign to Self
- Any ticket with 2+ AI keywords
- Medium priority in my Jira project keys
- Tickets related to agent infrastructure or LLM tooling

### Needs Info
- No description (can't estimate or start)
- Action: post in ticket asking for acceptance criteria — but write the message as a draft, never post automatically

### Monitor
- Low priority
- Not AI-related
- Already assigned to someone else

## Hard Rules
1. Never post a Jira comment automatically — write a draft first
2. Never close or delete a ticket
3. Never change priority without checking with the reporter
4. Flag tickets with no description as "Needs Info" — do not estimate

## Project Key Priorities
Fill in your project keys in order of importance (most important first).
These are read from USER.md → JIRA_PROJECT_KEYS.

## Voice for Drafted Messages
- Direct and brief
- State what's needed, no pleasantries
- Example: "Could you add an acceptance criteria? Happy to pick this up once clear."
