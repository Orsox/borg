"""Integration registry — tracks which integrations have credentials configured."""
import os
import pathlib
from dotenv import load_dotenv

# Resolve .env from project root (borg/.env), regardless of cwd
_ENV_FILE = pathlib.Path(__file__).parents[3] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

INTEGRATIONS: dict[str, dict] = {
    "obsidian": {
        "required_env": [],
        "description": "Local Obsidian vault — always on",
    },
    "jira": {
        "required_env": ["JIRA_URL", "JIRA_TOKEN"],
        "description": "Jira tickets and triage",
    },
    "polarion": {
        "required_env": ["POLARION_URL", "POLARION_TOKEN"],
        "description": "Polarion ALM work items",
    },
    "gitlab": {
        "required_env": ["GITLAB_URL", "GITLAB_TOKEN"],
        "description": "GitLab commits and MRs",
    },
    "teams": {
        "required_env": ["AZURE_CLIENT_ID", "AZURE_TENANT_ID"],
        "description": "Microsoft Teams messages",
    },
    "onedrive": {
        "required_env": ["AZURE_CLIENT_ID", "AZURE_TENANT_ID"],
        "description": "OneDrive files",
    },
}


def is_enabled(name: str) -> bool:
    if name not in INTEGRATIONS:
        return False
    return all(os.environ.get(k) for k in INTEGRATIONS[name]["required_env"])


def enabled_integrations() -> list[str]:
    return [name for name in INTEGRATIONS if is_enabled(name)]


def status_table() -> list[dict]:
    rows = []
    for name, info in INTEGRATIONS.items():
        enabled = is_enabled(name)
        missing = [k for k in info["required_env"] if not os.environ.get(k)]
        rows.append({
            "name": name,
            "enabled": enabled,
            "description": info["description"],
            "missing_env": missing,
        })
    return rows
