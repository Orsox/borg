#!/home/bernd/.claude/venv/bin/python3
"""Unified integration CLI — query all Second Brain integrations.

Usage:
  query.py status                          # show which integrations are enabled
  query.py obsidian recent [--days 3]
  query.py obsidian search <query>
  query.py obsidian read <path>
  query.py jira new [--days 3]
  query.py jira mine
  query.py jira overdue
  query.py polarion open [--project ID]
  query.py polarion changes [--days 1]
  query.py gitlab projects
  query.py gitlab commits <project/path> [--days 1]
  query.py gitlab mrs <project/path>
  query.py teams --auth                    # one-time interactive auth
  query.py teams mentions [--hours 24]
  query.py onedrive recent [--days 3]
  query.py onedrive search <query>
"""
import argparse
import pathlib
import sys

# Add scripts dir to path so integrations package resolves correctly
_SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS))


# ── helpers ──────────────────────────────────────────────────────────────────

def _check(name: str) -> bool:
    from integrations.registry import is_enabled
    if not is_enabled(name):
        print(f"  [{name}] not configured — add required credentials to .env")
        return False
    return True


def _guard(name: str):
    if not _check(name):
        sys.exit(1)


# ── subcommands ───────────────────────────────────────────────────────────────

def cmd_status(_args):
    from integrations.registry import status_table
    rows = status_table()
    col = max(len(r["name"]) for r in rows)
    print()
    for r in rows:
        icon = "✓" if r["enabled"] else "✗"
        name = r["name"].ljust(col)
        desc = r["description"]
        if r["missing_env"]:
            desc += f"  — needs: {', '.join(r['missing_env'])}"
        print(f"  {icon}  {name}  {desc}")
    print()


def cmd_obsidian(args):
    from integrations.obsidian import list_recent, search_title, read_note, format_context
    if args.obsidian_cmd == "recent":
        print(format_context(days=args.days))
    elif args.obsidian_cmd == "search":
        hits = search_title(args.query)
        if hits:
            for h in hits:
                print(f"  {h}")
        else:
            print("  No matches.")
    elif args.obsidian_cmd == "read":
        print(read_note(args.path))


def cmd_jira(args):
    _guard("jira")
    from integrations.jira import get_new_tickets, get_my_tickets, get_overdue, format_context
    if args.jira_cmd == "new":
        print(format_context())
    elif args.jira_cmd == "mine":
        tickets = get_my_tickets()
        if not tickets:
            print("  No open tickets assigned to you.")
            return
        print(f"## My Jira Tickets ({len(tickets)})")
        for t in tickets:
            print(f"  {t['key']}  [{t['status']}]  {t['summary']}")
    elif args.jira_cmd == "overdue":
        tickets = get_overdue()
        if not tickets:
            print("  No overdue tickets.")
            return
        print(f"## Overdue Tickets ({len(tickets)})")
        for t in tickets:
            print(f"  {t['key']}  due: {t.get('updated')}  {t['summary']}")


def cmd_polarion(args):
    _guard("polarion")
    from integrations.polarion import get_open_items, get_recent_changes, format_context
    if args.polarion_cmd == "open":
        items = get_open_items(project_id=getattr(args, "project", None))
        if not items:
            print("  No open Polarion work items.")
            return
        print(f"## Polarion — Open Items ({len(items)})")
        for i in items:
            print(f"  {i['id']}  [{i['type']}]  {i['title']}  | {i['status']}")
    elif args.polarion_cmd == "changes":
        print(format_context())


def cmd_gitlab(args):
    _guard("gitlab")
    from integrations.gitlab_client import get_my_projects, get_recent_commits, get_open_mrs, format_context
    if args.gitlab_cmd == "projects":
        projects = get_my_projects()
        for p in projects:
            print(f"  {p['path']}  (last activity: {p['last_activity']})")
    elif args.gitlab_cmd == "commits":
        commits = get_recent_commits(args.project, days=args.days)
        if not commits:
            print(f"  No commits in {args.project} in the last {args.days}d.")
            return
        for c in commits:
            print(f"  {c['time']}  {c['author']}: {c['message']}")
    elif args.gitlab_cmd == "mrs":
        mrs = get_open_mrs(args.project)
        if not mrs:
            print(f"  No open MRs in {args.project}.")
            return
        for mr in mrs:
            print(f"  !{mr['iid']}  {mr['author']}: {mr['title']}")
    elif args.gitlab_cmd == "summary":
        print(format_context(days=args.days))


def cmd_teams(args):
    if args.auth:
        from integrations.teams import authenticate
        authenticate()
        return
    _guard("teams")
    from integrations.teams import format_context
    print(format_context(hours=args.hours))


def cmd_onedrive(args):
    _guard("onedrive")
    from integrations.onedrive import list_recent, search_files, format_context
    if args.onedrive_cmd == "recent":
        print(format_context(days=args.days))
    elif args.onedrive_cmd == "search":
        hits = search_files(args.query)
        if not hits:
            print("  No files found.")
            return
        for f in hits:
            print(f"  {f['modified']}  {f['name']}")


# ── parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="query.py", description="Second Brain integration CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show which integrations are enabled")

    # Obsidian
    obs = sub.add_parser("obsidian")
    obs_sub = obs.add_subparsers(dest="obsidian_cmd", required=True)
    rec = obs_sub.add_parser("recent")
    rec.add_argument("--days", type=int, default=3)
    srch = obs_sub.add_parser("search")
    srch.add_argument("query")
    rd = obs_sub.add_parser("read")
    rd.add_argument("path")

    # Jira
    jira = sub.add_parser("jira")
    jira_sub = jira.add_subparsers(dest="jira_cmd", required=True)
    jn = jira_sub.add_parser("new")
    jn.add_argument("--days", type=int, default=3)
    jira_sub.add_parser("mine")
    jira_sub.add_parser("overdue")

    # Polarion
    pol = sub.add_parser("polarion")
    pol_sub = pol.add_subparsers(dest="polarion_cmd", required=True)
    po = pol_sub.add_parser("open")
    po.add_argument("--project", default=None)
    pch = pol_sub.add_parser("changes")
    pch.add_argument("--days", type=int, default=1)

    # GitLab
    gl = sub.add_parser("gitlab")
    gl_sub = gl.add_subparsers(dest="gitlab_cmd", required=True)
    gl_sub.add_parser("projects")
    glc = gl_sub.add_parser("commits")
    glc.add_argument("project")
    glc.add_argument("--days", type=int, default=1)
    glm = gl_sub.add_parser("mrs")
    glm.add_argument("project")
    gls = gl_sub.add_parser("summary")
    gls.add_argument("--days", type=int, default=1)

    # Teams
    teams = sub.add_parser("teams")
    teams.add_argument("--auth", action="store_true", help="Authenticate interactively")
    teams.add_argument("--hours", type=int, default=24)

    # OneDrive
    od = sub.add_parser("onedrive")
    od_sub = od.add_subparsers(dest="onedrive_cmd", required=True)
    odr = od_sub.add_parser("recent")
    odr.add_argument("--days", type=int, default=3)
    ods = od_sub.add_parser("search")
    ods.add_argument("query")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "status": cmd_status,
        "obsidian": cmd_obsidian,
        "jira": cmd_jira,
        "polarion": cmd_polarion,
        "gitlab": cmd_gitlab,
        "teams": cmd_teams,
        "onedrive": cmd_onedrive,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
