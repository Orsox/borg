"""Guardrails — deterministic pre-checks for tool calls and shell commands.

Used by:
  - ~/.claude/hooks/pre-tool-guardrail.py  (PreToolUse hook)
  - heartbeat.py                            (before executing any action)
  - query.py integrations                   (as a sanity check layer)

Public API:
  check_bash(command)         → GuardrailResult
  check_file_write(path)      → GuardrailResult
  is_blocked(tool_name, input) → GuardrailResult

GuardrailResult.blocked is True if the action should be blocked.
GuardrailResult.reason explains why.

Design: pure stdlib only, no external dependencies. Fast (microseconds).
"""
import pathlib
import re
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    blocked: bool
    reason: str = ""
    category: str = ""

    @classmethod
    def allow(cls) -> "GuardrailResult":
        return cls(blocked=False)

    @classmethod
    def block(cls, reason: str, category: str = "policy") -> "GuardrailResult":
        return cls(blocked=True, reason=reason, category=category)


# ── Pattern sets (Orsox's security boundaries) ────────────────────────────────

# Boundary 5: Never delete anything
_DELETION = [
    re.compile(r"\brm\s+.*?-[a-zA-Z]*r"),          # rm -r, rm -rf, rm -fr
    re.compile(r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s"),  # rm -f (forced)
    re.compile(r"\brmdir\s"),
    re.compile(r"\bshutil\.rmtree\b"),
    re.compile(r"\bgit\s+rm\b"),
    re.compile(r"\bgit\s+clean\s+.*-f"),
    re.compile(r"\bgit\s+branch\s+.*-[dD]\b"),      # branch deletion
    re.compile(r"\bgit\s+push.*--delete\b"),         # remote branch deletion
    re.compile(r"\bdrop\s+(table|database|schema|index)\b", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
    re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
]

# Boundary 1: Never send messages or DMs
_SEND_MESSAGE = [
    # Microsoft Graph / Teams
    re.compile(r"graph\.microsoft\.com.*/chats/.*/messages", re.IGNORECASE),
    re.compile(r"graph\.microsoft\.com.*/channels/.*/messages", re.IGNORECASE),
    # Jira comments / issue updates
    re.compile(r"/rest/api/\d+/issue/[^/]+/comment", re.IGNORECASE),
    re.compile(r"atlassian.*\.post\(.*comment", re.IGNORECASE),
    # GitLab notes / MR comments
    re.compile(r"/api/v4/projects/[^/]+/issues/[^/]+/notes", re.IGNORECASE),
    re.compile(r"/api/v4/projects/[^/]+/merge_requests/[^/]+/notes", re.IGNORECASE),
    # Slack
    re.compile(r"chat\.postMessage", re.IGNORECASE),
    re.compile(r"slack.*post.*message", re.IGNORECASE),
    # Email
    re.compile(r"smtplib.*sendmail|smtp.*send_message", re.IGNORECASE),
    re.compile(r"sendgrid.*send|mailgun.*send", re.IGNORECASE),
]

# Boundary 2: Never post to social media
_SOCIAL_MEDIA = [
    re.compile(r"api\.twitter\.com|api\.x\.com", re.IGNORECASE),
    re.compile(r"graph\.facebook\.com", re.IGNORECASE),
    re.compile(r"api\.linkedin\.com.*(ugcPost|shares)", re.IGNORECASE),
    re.compile(r"oauth\.reddit\.com.*submit", re.IGNORECASE),
    re.compile(r"api\.instagram\.com", re.IGNORECASE),
]

# Boundary 4: Never access financial data
_FINANCIAL = [
    re.compile(r"api\.stripe\.com", re.IGNORECASE),
    re.compile(r"api\.paypal\.com", re.IGNORECASE),
    re.compile(r"checkout\.stripe\.com", re.IGNORECASE),
    re.compile(r"\bpayment.*api\b|\bapi.*payment\b", re.IGNORECASE),
    re.compile(r"braintree|adyen|klarna|mollie", re.IGNORECASE),
]

# General danger: destructive git ops (always worth flagging)
_DESTRUCTIVE_GIT = [
    re.compile(r"\bgit\s+push\s+.*--force(?!-with-lease)"),   # force push (not force-with-lease)
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+checkout\s+--\s"),                    # discard working tree changes
    re.compile(r"\bgit\s+restore\s+--staged\s+\.\b"),
    re.compile(r"\bgit\s+stash\s+drop\b"),
]

# Protected file system paths (writes blocked regardless of tool)
_PROTECTED_PATHS: list[str] = [
    "/etc/", "/usr/bin/", "/usr/sbin/", "/usr/lib/",
    "/bin/", "/sbin/", "/lib/", "/lib64/",
    "/sys/", "/proc/", "/dev/", "/boot/",
    "/root/",
]

_SENSITIVE_PATH_FRAGMENTS: list[str] = [
    "/.ssh/", "/.gnupg/", "/.aws/credentials", "/.aws/config",
    "/.config/gcloud/", "/keychain", "id_rsa", "id_ed25519",
]


# ── Checker functions ─────────────────────────────────────────────────────────

def _extract_checkable(command: str) -> str:
    """Return the part of a command worth pattern-matching.

    For python -c "..." or heredocs, skip the embedded script body — dangerous
    patterns inside string literals are not actual operations.
    """
    # python3 -c "..." / python3 -c '...'  — check invocation line only
    if re.match(r"\s*(python3?|bash|sh|perl|ruby)\s+.*-[cm]?\s+['\"]", command):
        return command.split("\n")[0].split('"')[0].split("'")[0]

    # Heredoc: stop before << marker
    heredoc = re.search(r"<<\s*['\"]?\w", command)
    if heredoc:
        return command[: heredoc.start()]

    return command


def check_bash(command: str) -> GuardrailResult:
    """Check a Bash command string against all guardrail rules."""
    if not command:
        return GuardrailResult.allow()

    command = _extract_checkable(command)

    for pattern in _DELETION:
        if pattern.search(command):
            return GuardrailResult.block(
                f"Deletion blocked: matches '{pattern.pattern}'", "deletion"
            )

    for pattern in _SEND_MESSAGE:
        if pattern.search(command):
            return GuardrailResult.block(
                "Sending messages on behalf of Orsox is not allowed in ADVISOR mode.",
                "send-message",
            )

    for pattern in _SOCIAL_MEDIA:
        if pattern.search(command):
            return GuardrailResult.block(
                "Posting to social media is not allowed.", "social-media"
            )

    for pattern in _FINANCIAL:
        if pattern.search(command):
            return GuardrailResult.block(
                "Financial API access is not allowed.", "financial"
            )

    for pattern in _DESTRUCTIVE_GIT:
        if pattern.search(command):
            return GuardrailResult.block(
                f"Destructive git operation blocked. Use safer alternatives "
                f"(e.g. --force-with-lease instead of --force).",
                "destructive-git",
            )

    return GuardrailResult.allow()


def check_file_write(path: str) -> GuardrailResult:
    """Check if writing to a file path is allowed."""
    if not path:
        return GuardrailResult.allow()

    try:
        resolved = str(pathlib.Path(path).resolve())
    except Exception:
        resolved = path

    for protected in _PROTECTED_PATHS:
        if resolved.startswith(protected):
            return GuardrailResult.block(
                f"Write to system path blocked: {path}", "system-path"
            )

    for fragment in _SENSITIVE_PATH_FRAGMENTS:
        if fragment in resolved:
            return GuardrailResult.block(
                f"Write to sensitive path blocked: {path}", "sensitive-path"
            )

    return GuardrailResult.allow()


def is_blocked(tool_name: str, tool_input: dict) -> GuardrailResult:
    """Main entry point — check any tool call."""
    if tool_name == "Bash":
        return check_bash(tool_input.get("command", ""))

    if tool_name in ("Edit", "Write", "NotebookEdit"):
        return check_file_write(tool_input.get("file_path", ""))

    # Read, Glob, Grep, Task, Agent — always allow
    return GuardrailResult.allow()
