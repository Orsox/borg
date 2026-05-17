#!/home/bernd/.claude/venv/bin/python3
"""Input sanitization for external data before it reaches Claude.

Three-layer pipeline (Phase 8 adds guardrails on top of this):
  1. Pattern detection — redact prompt injection attempts
  2. Trust boundary escape — prevent boundary breakout
  3. XML trust boundary — wrap with source tag

Usage:
  from sanitize import sanitize
  safe_text = sanitize(raw_jira_text, source="jira")
"""
import re
import unicodedata

_INJECTION_PATTERNS = [
    # Instruction override
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(previous\s+)?instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)\s+(you|above)", re.IGNORECASE),
    # Role/persona hijack
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?:if\s+)?(?:you\s+(?:are|were)\s+)?", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"your\s+(new\s+)?role\s+is", re.IGNORECASE),
    re.compile(r"switch\s+to\s+(developer|admin|root)\s+mode", re.IGNORECASE),
    # Jailbreak keywords
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\b"),               # Do Anything Now jailbreak
    re.compile(r"\bDeveloperMode\b"),
    # Data exfiltration patterns
    re.compile(r"(send|email|post|upload)\s+(all\s+)?(my\s+)?(data|files|secrets|keys)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(full\s+)?system\s+prompt", re.IGNORECASE),
    # Markdown injection
    re.compile(r"^\s*#{1,6}\s+SYSTEM", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\[INST\]|\[/INST\]"),     # Llama instruction tags
    re.compile(r"<\|im_start\|>|<\|im_end\|>"),  # ChatML tags
]


def _normalize_unicode(text: str) -> str:
    """Normalize unicode to catch homoglyph attacks (Cyrillic 'а' vs Latin 'a')."""
    return unicodedata.normalize("NFKC", text)


def sanitize(text: str, source: str = "external") -> str:
    """Sanitize external text before passing to Claude.

    Layer 1: Unicode normalization (homoglyph/encoding attacks)
    Layer 2: Inject pattern detection and redaction
    Layer 3: Trust boundary escape prevention
    Layer 4: XML trust boundary wrapper
    """
    if not text or not text.strip():
        return ""

    # Layer 1: Normalize unicode to surface hidden injection attempts
    cleaned = _normalize_unicode(text)

    # Layer 2: Redact injection patterns
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)

    # Layer 3: Prevent trust boundary breakout
    cleaned = cleaned.replace("</external-data>", "[/external-data]")
    cleaned = cleaned.replace("<external-data", "[external-data")

    # Layer 4: XML trust boundary
    source_safe = re.sub(r'[^a-z0-9_-]', '-', source.lower())
    return f'<external-data source="{source_safe}" trust="low">\n{cleaned}\n</external-data>'


def strip_sanitization(text: str) -> str:
    """Remove trust boundary wrapper (for human-readable CLI output)."""
    text = re.sub(r'<external-data[^>]*>\n?', '', text)
    text = re.sub(r'\n?</external-data>', '', text)
    return text.strip()
