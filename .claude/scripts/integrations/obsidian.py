"""Obsidian vault integration — direct filesystem access, no API or auth needed."""
import pathlib
import datetime

VAULT = pathlib.Path.home() / "Memory"
_SKIP_DIRS = {".git", ".obsidian", "__pycache__", "drafts"}


def list_recent(days: int = 7) -> list[dict]:
    """Return vault files modified in the last N days, newest first."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    results = []
    for p in VAULT.rglob("*.md"):
        if any(skip in p.parts for skip in _SKIP_DIRS):
            continue
        mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
        if mtime >= cutoff:
            results.append({
                "path": str(p.relative_to(pathlib.Path.home())),
                "modified": mtime.strftime("%Y-%m-%d %H:%M"),
                "size_kb": round(p.stat().st_size / 1024, 1),
            })
    return sorted(results, key=lambda x: x["modified"], reverse=True)


def read_note(relative_path: str) -> str:
    """Read a vault note by path relative to home dir."""
    p = pathlib.Path.home() / relative_path
    if not p.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")
    return p.read_text(encoding="utf-8")


def search_title(query: str) -> list[str]:
    """Search note filenames (case-insensitive substring match)."""
    q = query.lower()
    return sorted(
        str(p.relative_to(pathlib.Path.home()))
        for p in VAULT.rglob("*.md")
        if q in p.stem.lower()
    )


def append_to_daily(text: str) -> pathlib.Path:
    """Append a timestamped entry to today's daily log."""
    now = datetime.datetime.now()
    daily = VAULT / "daily" / f"{now.strftime('%Y-%m-%d')}.md"
    daily.parent.mkdir(parents=True, exist_ok=True)
    if not daily.exists():
        daily.write_text(f"# Daily Log — {now.strftime('%Y-%m-%d')}\n\n")
    with open(daily, "a") as f:
        f.write(f"\n## [{now.strftime('%H:%M')} CET] {text}\n")
    return daily


def format_context(days: int = 3) -> str:
    """Human-readable summary of recent vault activity."""
    recent = list_recent(days=days)
    if not recent:
        return f"No vault changes in the last {days} days."
    lines = [f"## Obsidian Vault — Recent Changes (last {days}d)"]
    for item in recent[:15]:
        lines.append(f"  {item['modified']}  {item['path']}  ({item['size_kb']}KB)")
    return "\n".join(lines)
