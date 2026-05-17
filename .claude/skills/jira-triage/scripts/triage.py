#!/home/bernd/.claude/venv/bin/python3
"""Jira triage script — fetch new tickets, score by AI-relevance, write draft.

Usage:
  triage.py                    # fetch new tickets and write draft
  triage.py --days 5           # look back 5 days instead of 3
  triage.py --dry-run          # print scored tickets, don't write draft
  triage.py --projects AI,PLT  # override project keys

Draft written to: ~/Memory/drafts/active/YYYY-MM-DD_jira-triage.md
"""
import argparse
import datetime
import pathlib
import sys

# Add scripts dir to path
_SCRIPTS = pathlib.Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

VAULT = pathlib.Path.home() / "Memory"
DRAFTS_DIR = VAULT / "drafts" / "active"

# Keywords that signal AI/agent relevance → score boost
AI_KEYWORDS = [
    "agent", "llm", "ai", "model", "embedding", "vector", "rag",
    "claude", "gpt", "openai", "anthropic", "prompt", "inference",
    "fine-tun", "neural", "transformer", "langchain", "pipeline",
]

PRIORITY_SCORES = {
    "Critical": 10,
    "Blocker": 10,
    "High": 5,
    "Medium": 2,
    "Low": 0,
    "Lowest": 0,
}


def score_ticket(ticket: dict) -> tuple[int, list[str]]:
    """Return (score, reasons). Higher = more urgent/important."""
    score = 0
    reasons = []

    text = f"{ticket['summary']} {ticket.get('description_preview', '')}".lower()

    # Priority boost
    pri_score = PRIORITY_SCORES.get(ticket.get("priority", ""), 0)
    if pri_score:
        score += pri_score
        reasons.append(f"priority:{ticket['priority']}")

    # AI/agent relevance boost
    matched_kw = [kw for kw in AI_KEYWORDS if kw in text]
    if matched_kw:
        score += len(matched_kw) * 2
        reasons.append(f"AI-related:{','.join(matched_kw[:3])}")

    # Unassigned penalty — needs attention
    if ticket.get("assignee") == "Unassigned":
        score += 3
        reasons.append("unassigned")

    # Missing description flag — will need info before work can start
    if not ticket.get("description_preview", "").strip():
        score -= 2
        reasons.append("no-description")

    return score, reasons


def categorize(tickets: list[dict]) -> dict[str, list[dict]]:
    """Sort scored tickets into action categories."""
    scored = []
    for t in tickets:
        s, reasons = score_ticket(t)
        scored.append({**t, "_score": s, "_reasons": reasons})

    scored.sort(key=lambda x: -x["_score"])

    categories: dict[str, list[dict]] = {
        "action_now": [],    # high score, unassigned or critical
        "assign_self": [],   # AI-related, medium priority
        "needs_info": [],    # no description
        "monitor": [],       # everything else
    }

    for t in scored:
        if t.get("description_preview", "").strip() == "" and t["_score"] < 0:
            categories["needs_info"].append(t)
        elif t["_score"] >= 10 or (t["_score"] >= 5 and t.get("assignee") == "Unassigned"):
            categories["action_now"].append(t)
        elif t["_score"] >= 4 or "AI-related" in " ".join(t["_reasons"]):
            categories["assign_self"].append(t)
        else:
            categories["monitor"].append(t)

    return categories


def format_draft(categories: dict[str, list[dict]], project_keys: list[str]) -> str:
    now = datetime.datetime.now()
    projects_str = ", ".join(project_keys) if project_keys else "all"

    lines = [
        "---",
        "type: jira-triage",
        f'created: {now.strftime("%Y-%m-%dT%H:%M:%S+02:00")}',
        "status: active",
        "---",
        "",
        f"# Jira Triage — {now.strftime('%Y-%m-%d')}",
        f"Projects: {projects_str}",
        "",
    ]

    def ticket_lines(t: dict, suggestion: str) -> list[str]:
        pri = f"[{t['priority']}] " if t.get("priority") else ""
        reason_str = " | ".join(t["_reasons"]) if t["_reasons"] else ""
        result = [
            f"- **{t['key']}** {pri}— {t['summary']}",
            f"  Assignee: {t['assignee']} | Created: {t['created']}",
        ]
        if reason_str:
            result.append(f"  Signals: {reason_str}")
        if t.get("description_preview"):
            result.append(f"  > {t['description_preview'][:120]}…" if len(t.get("description_preview", "")) > 120 else f"  > {t['description_preview']}")
        result.append(f"  → **{suggestion}**")
        return result

    if categories["action_now"]:
        lines += [f"## Action Now ({len(categories['action_now'])} tickets)", ""]
        for t in categories["action_now"]:
            lines += ticket_lines(t, "Assign and start — high priority or critical")
            lines.append("")

    if categories["assign_self"]:
        lines += [f"## Assign to Self ({len(categories['assign_self'])} tickets)", ""]
        for t in categories["assign_self"]:
            lines += ticket_lines(t, "Relevant to your AI work — pick up in this sprint")
            lines.append("")

    if categories["needs_info"]:
        lines += [f"## Needs Info ({len(categories['needs_info'])} tickets)", ""]
        for t in categories["needs_info"]:
            lines += ticket_lines(t, "No description — ping reporter before accepting")
            lines.append("")

    if categories["monitor"]:
        lines += [f"## Monitor ({len(categories['monitor'])} tickets)", ""]
        for t in categories["monitor"]:
            pri = f"[{t['priority']}] " if t.get("priority") else ""
            lines.append(f"- **{t['key']}** {pri}— {t['summary']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Triage new Jira tickets")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--projects", default=None, help="Comma-separated project keys")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from integrations.registry import is_enabled
    if not is_enabled("jira"):
        print("ERROR: Jira not configured. Add JIRA_URL and JIRA_TOKEN to borg/.env")
        sys.exit(1)

    from integrations.jira import get_new_tickets, _load_project_keys
    project_keys = [k.strip() for k in args.projects.split(",")] if args.projects else _load_project_keys()

    print(f"Fetching tickets (last {args.days}d)…")
    tickets = get_new_tickets(project_keys=project_keys, days=args.days)

    if not tickets:
        print("No new tickets found.")
        return

    print(f"Found {len(tickets)} ticket(s). Scoring…")
    categories = categorize(tickets)

    # Summary to stdout
    total = sum(len(v) for v in categories.values())
    print(f"\nTriage summary:")
    print(f"  Action now:   {len(categories['action_now'])}")
    print(f"  Assign self:  {len(categories['assign_self'])}")
    print(f"  Needs info:   {len(categories['needs_info'])}")
    print(f"  Monitor:      {len(categories['monitor'])}")

    if args.dry_run:
        print("\n[dry-run] Draft not written.")
        return

    draft_text = format_draft(categories, project_keys)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    draft_path = DRAFTS_DIR / f"{today}_jira-triage.md"
    draft_path.write_text(draft_text)

    print(f"\nDraft written to: {draft_path}")
    print("Review it and take action — nothing has been posted to Jira.")


if __name__ == "__main__":
    main()
