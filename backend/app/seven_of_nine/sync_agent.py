"""Seven of Nine's specialized peer-sync comparison agent.

The "Sync Comparator Drone": a code-level agent that drives Seven's own LLM (no
pi/Docker — direct reasoning, since the task is pure text comparison) to analyse a
changed item between two BorgOS instances. It owns three focused skills:

  - semantic_compare    — what differs beyond the literal text
  - merge_recommendation — which side should win + merge notes
  - risk_assessment     — breaking-change / safety call before applying foreign content

`compare()` orchestrates the three into a single SyncAnalysis. The agent receives a
`chat_fn` (the same shape as LlmClient.chat) so it stays testable with a stub.
"""

import logging
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# (messages, system_prompt) -> assistant text — matches discord_bot.llm.LlmClient.chat
ChatFn = Callable[[list[dict[str, str]], str], Awaitable[str]]

SYNC_SKILL_DEFINITIONS = [
    (
        "sync-semantic-compare",
        "Vergleicht zwei Versionen eines Archon-Assets/Skills semantisch und benennt die echten Unterschiede.",
    ),
    (
        "sync-merge-recommendation",
        "Empfiehlt, welche Version (lokal/remote) übernommen werden sollte, mit Merge-Hinweisen.",
    ),
    (
        "sync-risk-assessment",
        "Bewertet das Risiko, fremde Inhalte zu übernehmen — Breaking Changes, Sicherheit.",
    ),
]


class SyncComparatorDrone:
    """Seven's specialized comparison agent for peer sync."""

    SYSTEM_PROMPT = (
        "Du bist eine spezialisierte Vergleichs-Drohne von Seven of Nine, eingesetzt für "
        "BorgOS Peer-Sync. Du erhältst zwei Versionen eines Archon-Assets, Skills oder Agenten "
        "— eine lokale und eine von einer anderen BorgOS-Instanz. Analysiere präzise und "
        "unverblümt, ohne Floskeln. Nenne Wahrscheinlichkeiten, Trade-offs und Risiken direkt. "
        "Wenn die Daten unzureichend sind, sage das. Antworte knapp."
    )

    def __init__(self, chat_fn: ChatFn) -> None:
        self._chat = chat_fn

    async def _ask(self, instruction: str) -> str:
        return await self._chat([{"role": "user", "content": instruction}], self.SYSTEM_PROMPT)

    @staticmethod
    def _block(kind: str, identity: str, local: str | None, remote: str | None) -> str:
        return (
            f"Art: {kind}\nIdentität: {identity}\n\n"
            f"--- LOKALE VERSION ---\n{local or '(fehlt)'}\n\n"
            f"--- REMOTE VERSION ---\n{remote or '(fehlt)'}\n"
        )

    async def semantic_compare(
        self, kind: str, identity: str, local: str | None, remote: str | None
    ) -> str:
        """Skill: what actually differs between the two versions."""
        return await self._ask(
            "Vergleiche die beiden Versionen und beschreibe in 1-4 Sätzen die inhaltlichen "
            "Unterschiede (nicht nur Textdiff — was ändert sich an Verhalten/Konfiguration?).\n\n"
            + self._block(kind, identity, local, remote)
        )

    async def merge_recommendation(
        self, kind: str, identity: str, local: str | None, remote: str | None
    ) -> dict:
        """Skill: which side should win + merge notes."""
        text = await self._ask(
            "Empfiehl, welche Version übernommen werden soll. Beginne deine Antwort mit GENAU "
            "EINER Zeile im Format 'WINNER: local' oder 'WINNER: remote' oder 'WINNER: merge'. "
            "Danach 1-3 Sätze Begründung / Merge-Hinweise.\n\n"
            + self._block(kind, identity, local, remote)
        )
        winner = "unknown"
        notes = text.strip()
        first, _, rest = text.strip().partition("\n")
        if first.lower().startswith("winner:"):
            candidate = first.split(":", 1)[1].strip().lower()
            if candidate in ("local", "remote", "merge"):
                winner = candidate
            notes = rest.strip() or notes
        return {"winner": winner, "merge_notes": notes}

    async def risk_assessment(
        self, kind: str, identity: str, local: str | None, remote: str | None
    ) -> str:
        """Skill: safety call before writing remote content locally."""
        return await self._ask(
            "Bewerte das Risiko, die REMOTE-Version lokal zu übernehmen: mögliche Breaking "
            "Changes, Sicherheitsbedenken, Abhängigkeiten. 1-3 Sätze. Wenn risikoarm, sage das.\n\n"
            + self._block(kind, identity, local, remote)
        )

    async def compare(
        self, kind: str, identity: str, local: str | None, remote: str | None
    ) -> dict:
        """Orchestrate the three skills into a SyncAnalysis dict."""
        semantic = await self.semantic_compare(kind, identity, local, remote)
        recommendation = await self.merge_recommendation(kind, identity, local, remote)
        risk = await self.risk_assessment(kind, identity, local, remote)
        return {
            "semantic_summary": semantic,
            "recommendation": recommendation,
            "risk": risk,
        }


async def seed_sync_skills(db: AsyncSession) -> None:
    """Register the comparator's three skills as visible Skill DB rows.

    The executable logic lives in SyncComparatorDrone; these rows are the visible
    registry (category 'sync-comparison', tagged 'seven') so the operator sees
    Seven's sync toolkit in the Skills UI. Idempotent.
    """
    from app.skills import service as skills_service

    for name, description in SYNC_SKILL_DEFINITIONS:
        try:
            existing = await skills_service.get_skill_by_name(db, name)
            if existing:
                continue
            await skills_service.create_skill(
                db,
                name=name,
                description=description,
                category="sync-comparison",
                tags=["seven", "sync"],
            )
        except Exception:
            # Seeding must never block startup (duplicate races, FS issues, ...).
            logger.exception("Failed to seed sync skill '%s'", name)
