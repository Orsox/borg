#!/home/bernd/.claude/venv/bin/python3
"""Heartbeat — Orsox's proactive monitoring loop.

Runs every 30 minutes via systemd timer (07:00–20:00 CET).
Gathers data from all enabled integrations, diffs against last run,
uses Claude to reason over new items, writes drafts for Orsox's review.

ADVISOR mode: drafts only — never sends, never posts, never deletes.

Usage:
  heartbeat.py              # normal run
  heartbeat.py --force      # skip time check, process everything
  heartbeat.py --dry-run    # gather + diff, skip Claude + drafts
  heartbeat.py --reset      # clear state (treat everything as new)
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys

# Add scripts dir so integrations package resolves
_SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS))

from dotenv import load_dotenv
load_dotenv(_SCRIPTS.parent / ".env")

VAULT = pathlib.Path.home() / "Memory"
STATE_FILE = pathlib.Path.home() / ".claude" / "data" / "state" / "heartbeat-state.json"
DRAFTS_ACTIVE = VAULT / "drafts" / "active"
DRAFTS_EXPIRED = VAULT / "drafts" / "expired"
DAILY_LOG = VAULT / "daily"

WORK_START = 7    # 07:00 CET
WORK_END = 20     # 20:00 CET
NUDGE_HOUR = 17
NUDGE_MINUTE = 30

# ── Time helpers ──────────────────────────────────────────────────────────────

def now_cet() -> datetime.datetime:
    return datetime.datetime.now()  # host must be in Berlin timezone


def is_work_hours() -> bool:
    h = now_cet().hour
    return WORK_START <= h < WORK_END


def is_nudge_time() -> bool:
    n = now_cet()
    return n.hour == NUDGE_HOUR and n.minute >= NUDGE_MINUTE


# ── State management ──────────────────────────────────────────────────────────

def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


# ── Data gathering ────────────────────────────────────────────────────────────

def gather_data() -> tuple[dict, dict]:
    """Return (snapshot_ids, full_data).

    snapshot_ids: minimal state for diffing (IDs only)
    full_data: complete data for Claude context
    """
    from integrations.registry import is_enabled
    snapshot: dict = {"timestamp": now_cet().isoformat()}
    full: dict = {}

    # Jira
    if is_enabled("jira"):
        try:
            from integrations.jira import get_new_tickets
            tickets = get_new_tickets(days=3)
            snapshot["jira"] = [t["key"] for t in tickets]
            full["jira"] = tickets
        except Exception as e:
            _log(f"Jira gather error: {e}")

    # GitLab
    if is_enabled("gitlab"):
        try:
            from integrations.gitlab_client import get_my_projects, get_recent_commits, get_open_mrs
            projects = get_my_projects()
            snapshot["gitlab"] = {}
            full["gitlab"] = {}
            for p in projects[:10]:
                commits = get_recent_commits(p["path"], days=1)
                mrs = get_open_mrs(p["path"])
                snapshot["gitlab"][p["path"]] = [c["sha"] for c in commits]
                if commits or mrs:
                    full["gitlab"][p["path"]] = {"commits": commits, "mrs": mrs, "name": p["name"]}
        except Exception as e:
            _log(f"GitLab gather error: {e}")

    # Teams
    if is_enabled("teams"):
        try:
            from integrations.teams import get_recent_mentions
            mentions = get_recent_mentions(hours=1)  # only last hour per heartbeat cycle
            snapshot["teams"] = [f"{m['chat_id']}:{m['time']}" for m in mentions]
            full["teams"] = mentions
        except Exception as e:
            _log(f"Teams gather error: {e}")

    # Polarion
    if is_enabled("polarion"):
        try:
            from integrations.polarion import get_recent_changes
            items = get_recent_changes(days=1)
            snapshot["polarion"] = [i["id"] for i in items]
            full["polarion"] = items
        except Exception as e:
            _log(f"Polarion gather error: {e}")

    return snapshot, full


def compute_new_items(prev: dict, curr_snap: dict, full: dict) -> dict:
    """Return only items that are new since the last heartbeat."""
    new: dict = {}

    prev_jira = set(prev.get("jira", []))
    curr_jira = set(curr_snap.get("jira", []))
    new_jira_keys = curr_jira - prev_jira
    if new_jira_keys:
        new["jira"] = [t for t in full.get("jira", []) if t["key"] in new_jira_keys]

    prev_gitlab = prev.get("gitlab", {})
    curr_gitlab = curr_snap.get("gitlab", {})
    new_gitlab: dict = {}
    for path, shas in curr_gitlab.items():
        prev_shas = set(prev_gitlab.get(path, []))
        new_shas = set(shas) - prev_shas
        if new_shas and path in full.get("gitlab", {}):
            project_data = full["gitlab"][path]
            new_commits = [c for c in project_data["commits"] if c["sha"] in new_shas]
            new_gitlab[path] = {
                "commits": new_commits,
                "mrs": project_data["mrs"],
                "name": project_data["name"],
            }
    if new_gitlab:
        new["gitlab"] = new_gitlab

    prev_teams = set(prev.get("teams", []))
    curr_teams = set(curr_snap.get("teams", []))
    new_team_ids = curr_teams - prev_teams
    if new_team_ids:
        new["teams"] = [m for m in full.get("teams", [])
                        if f"{m['chat_id']}:{m['time']}" in new_team_ids]

    prev_polarion = set(prev.get("polarion", []))
    curr_polarion = set(curr_snap.get("polarion", []))
    new_pol_ids = curr_polarion - prev_polarion
    if new_pol_ids:
        new["polarion"] = [i for i in full.get("polarion", []) if i["id"] in new_pol_ids]

    return new


# ── Context formatting ────────────────────────────────────────────────────────

def format_context_for_claude(new_items: dict, habits_unchecked: list[str]) -> str:
    parts = ["# Heartbeat Context — New Items Since Last Run"]

    if new_items.get("jira"):
        parts.append(f"\n## New Jira Tickets ({len(new_items['jira'])})")
        for t in new_items["jira"]:
            parts.append(
                f"- **{t['key']}** [{t['priority']}] {t['summary']}\n"
                f"  Status: {t['status']} | Assignee: {t['assignee']} | Created: {t['created']}\n"
                f"  {t['description_preview'][:150] if t['description_preview'] else '(no description)'}"
            )

    if new_items.get("gitlab"):
        parts.append(f"\n## New GitLab Activity")
        for path, data in new_items["gitlab"].items():
            if data["commits"]:
                parts.append(f"\n### {path}")
                for c in data["commits"][:5]:
                    parts.append(f"  - {c['time']}  {c['author']}: {c['message']}")
            if data["mrs"]:
                parts.append(f"  Open MRs: {len(data['mrs'])}")
                for mr in data["mrs"][:2]:
                    parts.append(f"  - !{mr['iid']} {mr['author']}: {mr['title']}")

    if new_items.get("teams"):
        parts.append(f"\n## New Teams Mentions ({len(new_items['teams'])})")
        for m in new_items["teams"]:
            parts.append(f"- {m['time']}  From: {m['sender']}\n  {m['body'][:200]}")

    if new_items.get("polarion"):
        parts.append(f"\n## Polarion Changes ({len(new_items['polarion'])})")
        for i in new_items["polarion"]:
            parts.append(f"- {i['id']} [{i['type']}] {i['title']} — {i['status']}")

    if habits_unchecked:
        parts.append(f"\n## Unchecked Habit Pillars Today")
        for p in habits_unchecked:
            parts.append(f"- {p}")

    parts.append("""
---
## Instructions for Claude

You are operating in ADVISOR mode. Orsox reviews everything — you draft, never act.

For each actionable item above, decide:
1. Does this need a draft? (see SOUL.md drafting criteria)
2. If yes: write the draft in Orsox's voice — direct, technical, brief.

Format your response exactly like this:

NOTIFICATION: <one-line summary of most important thing, max 80 chars>

For each draft needed, use:

DRAFT_START
type: <jira-triage|teams-reply|gitlab-summary|general>
source_id: <ticket-key or message-id or project-path>
slug: <short-hyphenated-slug>
subject: <one-line topic>
---
<draft content — markdown, starting with ## heading>
DRAFT_END

HABITS_INSIGHT: <brief suggestion for any unchecked pillars based on today's activity, or "none">

If nothing needs a draft, just write:
NOTIFICATION: <summary>
NO_DRAFTS
HABITS_INSIGHT: <suggestion or "none">
""")

    return "\n".join(parts)


# ── Habits ────────────────────────────────────────────────────────────────────

def get_unchecked_habits() -> list[str]:
    habits_file = VAULT / "HABITS.md"
    if not habits_file.exists():
        return []
    unchecked = []
    in_today = False
    for line in habits_file.read_text().splitlines():
        if line.startswith("## Today"):
            in_today = True
        elif line.startswith("## ") and in_today:
            break  # past today's section
        elif in_today and "- [ ]" in line:
            # Extract pillar name (before the em dash)
            pillar = line.replace("- [ ]", "").strip()
            if "**" in pillar:
                pillar = pillar.split("**")[1]  # bold name
            unchecked.append(pillar)
    return unchecked


# ── Claude reasoning ──────────────────────────────────────────────────────────

def call_claude(context: str) -> str:
    import anthropic
    soul_path = VAULT / "SOUL.md"
    system = soul_path.read_text() if soul_path.exists() else "You are Orsox's AI second brain. ADVISOR mode: draft only, never act."

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": context}],
    )
    return msg.content[0].text


def parse_response(response: str) -> tuple[str, list[dict], str]:
    """Parse Claude's structured response.
    Returns (notification, drafts, habits_insight).
    """
    notification = "Heartbeat complete"
    drafts = []
    habits_insight = "none"

    for line in response.splitlines():
        if line.startswith("NOTIFICATION:"):
            notification = line[len("NOTIFICATION:"):].strip()
        elif line.startswith("HABITS_INSIGHT:"):
            habits_insight = line[len("HABITS_INSIGHT:"):].strip()

    # Parse DRAFT blocks
    import re
    draft_blocks = re.findall(r"DRAFT_START\n(.*?)\nDRAFT_END", response, re.DOTALL)
    for block in draft_blocks:
        lines = block.strip().splitlines()
        meta: dict = {}
        content_lines = []
        past_separator = False
        for line in lines:
            if line == "---":
                past_separator = True
                continue
            if not past_separator:
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            else:
                content_lines.append(line)
        if meta and content_lines:
            drafts.append({**meta, "content": "\n".join(content_lines).strip()})

    return notification, drafts, habits_insight


# ── Draft writing ─────────────────────────────────────────────────────────────

def write_draft(draft: dict):
    DRAFTS_ACTIVE.mkdir(parents=True, exist_ok=True)
    today = now_cet().strftime("%Y-%m-%d")
    slug = draft.get("slug", "draft")[:40]
    filename = f"{today}_{draft.get('type', 'general')}_{slug}.md"
    path = DRAFTS_ACTIVE / filename

    frontmatter = (
        "---\n"
        f"type: {draft.get('type', 'general')}\n"
        f"source_id: {draft.get('source_id', '')}\n"
        f"subject: {draft.get('subject', '')}\n"
        f"created: {now_cet().strftime('%Y-%m-%dT%H:%M:%S+02:00')}\n"
        "status: active\n"
        "---\n\n"
    )
    path.write_text(frontmatter + draft["content"])
    _log(f"Draft written: {path.name}")


def expire_old_drafts():
    """Move drafts/active/ files older than 24h to drafts/expired/."""
    if not DRAFTS_ACTIVE.exists():
        return
    DRAFTS_EXPIRED.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
    for f in DRAFTS_ACTIVE.glob("*.md"):
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            dest = DRAFTS_EXPIRED / f.name
            f.rename(dest)
            _log(f"Expired: {f.name}")


# ── Desktop notification ──────────────────────────────────────────────────────

def notify(message: str, urgency: str = "normal"):
    """Send a desktop notification via notify-send (Linux)."""
    try:
        subprocess.run(
            ["notify-send", "--urgency", urgency, "--app-name", "Second Brain", message],
            timeout=5,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # headless VPS — no display, silent skip


# ── Daily log ─────────────────────────────────────────────────────────────────

def _log(message: str):
    print(f"[{now_cet().strftime('%H:%M')}] {message}")
    # Also append to daily log
    today = now_cet().strftime("%Y-%m-%d")
    log_path = DAILY_LOG / f"{today}.md"
    DAILY_LOG.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(f"# Daily Log — {today}\n\n> Append-only. Timestamped entries.\n\n")


def _log_event(title: str, body: str = ""):
    n = now_cet()
    log_path = DAILY_LOG / f"{n.strftime('%Y-%m-%d')}.md"
    DAILY_LOG.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(f"# Daily Log — {n.strftime('%Y-%m-%d')}\n\n")
    with open(log_path, "a") as f:
        f.write(f"\n## [{n.strftime('%H:%M')} CET] [Heartbeat] {title}\n")
        if body:
            f.write(f"{body}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Skip work-hours check")
    parser.add_argument("--dry-run", action="store_true", help="No Claude call, no draft writes")
    parser.add_argument("--reset", action="store_true", help="Clear state (next run treats all as new)")
    args = parser.parse_args()

    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("State cleared.")
        return

    if not args.force and not is_work_hours():
        return  # silent exit outside 07:00–20:00

    _log("Heartbeat starting…")

    # 1. Expire old drafts
    expire_old_drafts()

    # 2. Gather data from all enabled integrations
    curr_snap, full_data = gather_data()

    # 3. Load previous state and diff
    prev_state = load_state()
    new_items = compute_new_items(prev_state, curr_snap, full_data)

    # 4. Check habits
    habits_unchecked = []
    if is_nudge_time() or args.force:
        habits_unchecked = get_unchecked_habits()

    total_new = sum(
        len(v) if isinstance(v, list) else len(v)
        for v in new_items.values()
    )

    if total_new == 0 and not habits_unchecked:
        _log("Nothing new — skipping Claude call.")
        save_state(curr_snap)
        return

    _log(f"New items: {total_new}, unchecked habits: {len(habits_unchecked)}")

    if args.dry_run:
        print(json.dumps({"new_items": {k: len(v) if isinstance(v, list) else list(v.keys()) for k, v in new_items.items()}, "habits_unchecked": habits_unchecked}, indent=2))
        save_state(curr_snap)
        return

    # 5. Check ANTHROPIC_API_KEY
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _log("ERROR: ANTHROPIC_API_KEY not set in .env — skipping Claude call.")
        save_state(curr_snap)
        return

    # 6. Format context and call Claude
    context = format_context_for_claude(new_items, habits_unchecked)
    _log("Calling Claude…")
    try:
        response = call_claude(context)
    except Exception as e:
        _log(f"Claude error: {e}")
        save_state(curr_snap)
        return

    # 7. Parse response
    notification, drafts, habits_insight = parse_response(response)

    # 8. Write drafts
    for draft in drafts:
        write_draft(draft)

    # 9. Log to daily log
    draft_names = [d.get("slug", "?") for d in drafts]
    body = f"- New items: {total_new}\n"
    if drafts:
        body += f"- Drafts written: {', '.join(draft_names)}\n"
    if habits_insight and habits_insight != "none":
        body += f"- Habits insight: {habits_insight}\n"
    _log_event(notification, body)

    # 10. Desktop notification
    msg = notification
    if drafts:
        msg += f" ({len(drafts)} draft{'s' if len(drafts) != 1 else ''} in drafts/active/)"
    if habits_unchecked and habits_insight != "none":
        notify(f"Habit nudge: {habits_insight[:80]}", urgency="low")
    notify(msg)

    # 11. Save state
    save_state(curr_snap)
    _log(f"Done. Notification: {notification}")


if __name__ == "__main__":
    main()
