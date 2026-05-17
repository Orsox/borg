#!/home/bernd/.claude/venv/bin/python3
"""Daily reflection — runs at 08:00 CET via systemd timer.

Two jobs:
  1. MEMORY.md curation: read yesterday's daily log, promote key decisions/facts.
  2. HABITS.md reset: archive yesterday's checklist, create fresh one for today.

Usage:
  memory_reflect.py            # reflect on yesterday
  memory_reflect.py --date YYYY-MM-DD  # reflect on a specific day
  memory_reflect.py --dry-run  # print what would be promoted, don't write
"""
import argparse
import datetime
import os
import pathlib
import re
import sys

_SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS))

from dotenv import load_dotenv
load_dotenv(_SCRIPTS.parent / ".env")

VAULT = pathlib.Path.home() / "Memory"
MEMORY_MD = VAULT / "MEMORY.md"
HABITS_MD = VAULT / "HABITS.md"
DAILY_DIR = VAULT / "daily"
MAX_MEMORY_BYTES = 3000  # ~3KB limit for MEMORY.md


# ── Habits management ─────────────────────────────────────────────────────────

def reset_habits(today: datetime.datetime, dry_run: bool = False):
    """Archive yesterday's checklist and create a fresh one for today."""
    if not HABITS_MD.exists():
        return

    text = HABITS_MD.read_text()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # Extract today's checklist block
    today_match = re.search(r"## Today — .*?\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not today_match:
        print("HABITS.md: no 'Today' section found — skipping reset.")
        return

    today_block = today_match.group(1).strip()

    # Build archived version of yesterday's block
    archive_entry = f"\n### {yesterday_str}\n{today_block}\n"

    # Build new today's block (reset all checkboxes)
    new_today_block = re.sub(r"- \[x\]", "- [ ]", today_block)
    new_today_section = f"## Today — {today_str}\n{new_today_block}"

    # Replace the today section and append to History
    new_text = re.sub(
        r"## Today — .*?\n.*?(?=\n## |\Z)",
        new_today_section,
        text,
        flags=re.DOTALL,
        count=1,
    )

    # Append to History section
    if "## History" in new_text:
        new_text = new_text.replace("## History\n", f"## History\n{archive_entry}")
    else:
        new_text += f"\n## History\n{archive_entry}"

    if dry_run:
        print(f"[dry-run] HABITS.md: would archive {yesterday_str} and reset for {today_str}")
        return

    HABITS_MD.write_text(new_text)
    print(f"HABITS.md: reset for {today_str}, {yesterday_str} archived.")


# ── Memory promotion ──────────────────────────────────────────────────────────

def load_daily_log(date: datetime.datetime) -> str | None:
    path = DAILY_DIR / f"{date.strftime('%Y-%m-%d')}.md"
    if not path.exists():
        return None
    return path.read_text()


def call_claude_for_reflection(log_text: str, date_str: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Review this daily log from {date_str} and extract items worth long-term retention in MEMORY.md.

DAILY LOG:
{log_text}

MEMORY.md should contain:
- Key architectural or technical decisions made
- Important facts learned (non-obvious, will matter in future sessions)
- Project status updates (with date)
- Lessons learned from failures or surprises
- Team context changes

DO NOT include:
- Routine log entries (session start/end, compaction events)
- Things already obvious from reading the code
- Temporary status that will change soon

Format your response as a markdown list. Each item on its own line starting with "- ".
If nothing is worth promoting, respond with exactly: NOTHING_TO_PROMOTE
Keep each item under 120 characters. Include the date prefix: [{date_str}]"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def update_memory_md(new_items: list[str], section: str = "Key Decisions"):
    """Append promoted items to MEMORY.md, pruning if over size limit."""
    if not MEMORY_MD.exists():
        print("MEMORY.md not found — skipping promotion.")
        return

    text = MEMORY_MD.read_text()

    # Append to the target section
    if f"## {section}" in text:
        insertion = "\n".join(new_items) + "\n"
        text = text.replace(
            f"## {section}\n",
            f"## {section}\n{insertion}",
            1,
        )
    else:
        text += f"\n## {section}\n" + "\n".join(new_items) + "\n"

    # Prune if over size limit — remove oldest "In Progress" entries first
    while len(text.encode()) > MAX_MEMORY_BYTES:
        # Find oldest bullet in "In Progress (This Week)" and remove it
        match = re.search(r"(## In Progress.*?\n)(- \[[ x]\] .*?\n)", text, re.DOTALL)
        if match:
            text = text[:match.start(2)] + text[match.end(2):]
        else:
            break  # can't prune further — MEMORY.md is genuinely too large

    MEMORY_MD.write_text(text)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Reflect on YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = datetime.datetime.now()
    if args.date:
        target = datetime.datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target = today - datetime.timedelta(days=1)

    target_str = target.strftime("%Y-%m-%d")
    print(f"Reflecting on {target_str}…")

    # 1. Reset HABITS.md (always, even if no log exists)
    reset_habits(today, dry_run=args.dry_run)

    # 2. Load yesterday's daily log
    log_text = load_daily_log(target)
    if not log_text:
        print(f"No daily log for {target_str} — nothing to promote.")
        return

    # Strip auto-entries that aren't worth promoting
    lines = [
        line for line in log_text.splitlines()
        if not any(skip in line for skip in [
            "[Auto] Session ended",
            "[Auto] Context compacted",
            "[Auto] Pre-compact",
        ])
    ]
    meaningful_log = "\n".join(lines).strip()

    if len(meaningful_log) < 100:
        print("Daily log too short to extract anything meaningful.")
        return

    # 3. Check ANTHROPIC_API_KEY
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set — skipping Claude promotion.")
        return

    # 4. Ask Claude what's worth keeping
    print("Asking Claude to identify key items…")
    response = call_claude_for_reflection(meaningful_log, target_str)

    if response == "NOTHING_TO_PROMOTE":
        print("Nothing worth promoting to MEMORY.md today.")
        return

    # Parse into list items
    items = [line.strip() for line in response.splitlines() if line.strip().startswith("-")]

    if not items:
        print("No structured items returned.")
        return

    print(f"Items to promote ({len(items)}):")
    for item in items:
        print(f"  {item}")

    if args.dry_run:
        print("[dry-run] Not writing to MEMORY.md.")
        return

    # 5. Write to MEMORY.md
    update_memory_md(items, section="Key Decisions")
    print(f"Promoted {len(items)} item(s) to MEMORY.md.")

    # Re-index vault after update
    try:
        subprocess.run(
            [str(pathlib.Path.home() / ".local" / "bin" / "mindex")],
            timeout=60,
            capture_output=True,
        )
    except Exception:
        pass  # non-critical


import subprocess  # noqa: E402 — needed by main()

if __name__ == "__main__":
    main()
