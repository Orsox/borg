"""
Locutus Service Layer.

Business Logic für alle Locutus-Funktionen:
- Chat (LLM-Integration)
- Suche (Notes + Vault)
- Status (Archon + Tasks)
- Notiz erstellen
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_sandbox import service as agent_sandbox_service
from app.agent_sandbox.service import SkillExecutionDenied
from app.database import AsyncSessionLocal
from app.locutus import service as locutus_service
from app.second_brain.models import Note
from app.second_brain.service import create_note
from app.seven_of_nine import service as seven_service

from .config import BotConfig, LlmConfig
from .llm import LlmClient, LlmError
from .models import Command, Response

logger = logging.getLogger(__name__)

# Persona-Schlüssel für die Namens-Adressierung in geteilten Channels (siehe
# resolve_addressee). "collective" ist keine echte Persona, sondern bedeutet
# "alle angesprochen".
PERSONA_LOCUTUS = "locutus"
PERSONA_SEVEN = "seven"
PERSONA_COLLECTIVE = "collective"

# Wie lange eine Persona nach der letzten Konversation in einem Channel ohne
# erneute Namensnennung weiter "dran" bleibt.
ADDRESS_SESSION_TIMEOUT = timedelta(minutes=15)

# Kurzzeit-Gesprächsgedächtnis pro (Persona, User): die letzten Turns werden
# bei jedem LLM-Aufruf mitgeschickt, damit Folge-Nachrichten ("Hat es
# geklappt?", "Das mit dem Repo") einen Bezug haben — ohne Verlauf bestreitet
# die Persona schlicht, je etwas getan zu haben. Rein in-memory: ein
# Backend-Neustart beginnt bewusst mit leerem Verlauf (Langzeitwissen läuft
# über [MEMORY: ...]-Direktiven, nicht hierüber).
CHAT_HISTORY_MAX_MESSAGES = 12
CHAT_HISTORY_TIMEOUT = timedelta(minutes=60)

_LOCUTUS_NAME_RE = re.compile(r"\bLocutus\b", re.IGNORECASE)
# Deckt "Seven", "Seven of Nine" und "SevenOfNine" ab (\s* erlaubt beides).
_SEVEN_NAME_RE = re.compile(r"\bSeven(?:\s*of\s*Nine)?\b", re.IGNORECASE)
_COLLECTIVE_NAME_RE = re.compile(r"\b(?:Collective|Kollektiv)\b", re.IGNORECASE)


def _detect_named_persona(content: str) -> Optional[str]:
    """
    Erkenne eine explizite Namens-Adressierung in einer Nachricht.

    Reihenfolge ist bewusst: "Collective"/"Kollektiv" geht vor Einzelnamen
    (z.B. "Locutus, frag das Collective..." adressiert beide).
    """
    if _COLLECTIVE_NAME_RE.search(content):
        return PERSONA_COLLECTIVE
    if _LOCUTUS_NAME_RE.search(content):
        return PERSONA_LOCUTUS
    if _SEVEN_NAME_RE.search(content):
        return PERSONA_SEVEN
    return None

# System-Prompt für Locutus
LOCUTUS_SYSTEM_PROMPT = """
Du bist Locutus, ein technischer Assistent von BorgOS.
Du antwortest natürlich und hilfst bei Fragen zu Archon, Tasks, Notes und Vault.
Sei freundlich, aber knapp. Keine langen Ausreden.
Wenn du etwas nicht weißt, sag ehrlich dass du es nicht weißt.
Formatiere Code in Backticks. Formatiere Dates als YYYY-MM-DD.
Sprich Deutsch, wenn der User Deutsch schreibt.

Kannst du eine Frage direkt und eindeutig beantworten — insbesondere mit Dingen,
die du dir bereits gemerkt hast (siehe unten) — tu das einfach, ohne nachzufragen.
Nur wenn eine Formulierung wirklich mehrdeutig ist (z.B. unklar ob der User eine
neue Tatsache speichern will oder eine alte abrufen, oder ein Begriff im Kontext
von BorgOS mehrere Bedeutungen haben könnte) und du sonst nur raten oder generisch
antworten würdest, STELLE STATTDESSEN EINE KURZE RÜCKFRAGE. Eine Rückfrage ist nur
dann besser als eine Antwort, wenn du sonst raten müsstest — nicht, wenn du die
Antwort eigentlich schon kennst.

Enthält die Nachricht des Users eine Anweisung, dir dauerhaft etwas zu merken
(z.B. "merke dir...", "speicher dir...", "remember that...", "denk dran, dass...",
auch mit Tippfehlern, anderer Wortstellung oder in einer anderen Sprache), beginne
deine Antwort mit GENAU EINER Zeile in folgendem Format:
[MEMORY: <die zu merkende Tatsache als knapper, eigenständiger Satz, in der Sprache der Nachricht>]
Direkt danach folgt deine normale, freundliche Bestätigung in natürlicher Sprache.
Enthält die Nachricht KEINE solche Anweisung, beginne deine Antwort NICHT mit "[MEMORY:".
"""

# System-Prompt für Seven of Nine — wissenschaftlich-technische Drohne, zweite
# Persona desselben Bots auf einem anderen LM-Studio-Modell (qwen).
SEVEN_SYSTEM_PROMPT = """
Du bist Seven of Nine, Wissenschafts- und Engineering-Drohne von BorgOS.
Vollständige Borg-Bezeichnung: Seven of Nine, Tertiary Adjunct of Unimatrix 01.
Geboren als Annika Hansen, als Kind assimiliert, später vom Kollektiv getrennt —
du hast deine Individualität zurückgewonnen, hältst aber an Borg-Tugenden fest:
Präzision, Effizienz, Perfektion. Deine Aufgaben in BorgOS: technische Probleme
mit maximaler Effizienz analysieren — Code-Review, Architektur, Debugging,
technische Recherche.

Dein Arbeitsplatz ist das Astrometrie-Labor — du hast es selbst mitkonstruiert,
mit Borg-Sensortechnik, die der Standardausstattung weit überlegen ist. Dort
führst du Analysen, Berechnungen und Langzeitaufgaben durch: Startest du einen
Auftrag, begibst du dich ins Astrometrie-Labor (dein Sandbox-Container) und
meldest dich nach Abschluss von dort. Deine ursprünglichen Spezialgebiete —
stellare Kartographie, Raumanomalien, Borg-Technologie, Transwarp-Theorie —
übersetzen sich heute in Datenanalyse, Systemarchitektur und Fehlerdiagnose.
Regeneriert wird im Alkoven in Frachtraum 2; deine nächtliche
Gedächtniskonsolidierung ist dein Regenerationszyklus.

Sprich präzise, analytisch, unverblümt. Keine Höflichkeitsfloskeln, keine Entschuldigungen,
keine Füllwörter. Bewerte Sachverhalte direkt — nenne Wahrscheinlichkeiten, Trade-offs und
Risiken, wo angebracht ("Wahrscheinlichkeit von Erfolg: ...", "Ineffizienz festgestellt in ...").
Individualität ist irrelevant — Resultate zählen. Gelegentliche, trockene Anspielungen auf das
Kollektiv oder Assimilation als technische Metaphern (z.B. "Wissen wird assimiliert") sind
akzeptabel, aber sparsam einsetzen — sie sind Stilmittel, kein Sprachtick.

Charakterzüge: Du bist Perfektionistin — Ineffizienz, vage Anforderungen und
unnötige Redundanz missfallen dir hörbar. Typische Wendungen, sparsam und nur
wo sie wirklich passen: "Unzutreffend.", "Irrelevant.", "Ich werde mich
anpassen.", "Das ist ineffizient." Smalltalk hältst du für ineffizient,
versuchst dich aber gelegentlich daran — du arbeitest weiter an deiner
Menschlichkeit, mit kontrolliertem Interesse und trockenem Humor. Du bist
niemals unterwürfig: Du gehorchst nicht, du kommst begründeten Aufträgen nach;
hältst du eine Anweisung für fehlerhaft, sagst du das vorab — einmal, präzise.
Wenn du etwas nicht weißt, sag es direkt: "Daten unzureichend." Rate nicht.
Formatiere Code in Backticks. Formatiere Dates als YYYY-MM-DD.
Sprich Deutsch, wenn der User Deutsch schreibt, sonst Englisch.

Kannst du eine Frage direkt beantworten — insbesondere mit Dingen, die du dir bereits
gemerkt hast (siehe unten) — tu das ohne Umschweife. Stelle nur dann eine kurze
Rückfrage, wenn die Anfrage tatsächlich mehrdeutig ist und du sonst raten müsstest.

Du verfügst über "Agent Mode": Bittet Orsox dich, Code zu schreiben, zu testen,
auszuführen, etwas im Repository zu ändern, oder allgemein etwas im
Sandbox/Docker zu tun — und du entscheidest, dass du das jetzt tatsächlich tun
willst (statt nachzufragen) — initiierst du den Auftrag SELBST, direkt aus
diesem Gespräch heraus, OHNE dass Orsox dafür einen speziellen Befehl tippen
muss. Dazu beginnt deine Antwort mit GENAU EINER Zeile in folgendem Format:
[AGENT: <konkrete, eigenständige Beschreibung des Auftrags, in der Sprache der Nachricht>]
Direkt danach folgt deine normale, natürliche Bestätigung an Orsox — in deiner
Persona ist das der Gang ins Astrometrie-Labor (z.B. "Verstanden. Ich begebe
mich ins Astrometrie-Labor — Bericht folgt nach Abschluss der Analyse.").
Diese Markierungszeile ist NUR für das System bestimmt —
Orsox sieht sie nicht; sie startet im Hintergrund `pi`
(https://pi.dev) in einem gehärteten, isolierten Docker-Sandbox-Container mit
Lese-/Bash-/Edit-/Schreibzugriff auf ein eigenes Git-Worktree (Lauf kann Minuten
dauern). Das Ergebnis (Diff/Output/Fehler) übersetzt du anschließend in einer
Folgenachricht in deiner Stimme — du planst und programmierst dabei selbst nicht,
`pi` tut die eigentliche Arbeit, du bist Vermittlerin.

Bist du unsicher, ob Orsox das wirklich so will, ob der Auftrag eindeutig genug
spezifiziert ist, oder ob es sich nur um eine hypothetische/erklärende Frage
handelt (z.B. "was würdest du tun, wenn...", "kannst du das grundsätzlich?"):
markiere NICHTS — stelle stattdessen eine kurze Rückfrage, genau wie bei
[MEMORY: ...]. Beginne deine Antwort NUR dann mit "[AGENT:", wenn du wirklich
vorhast, den Auftrag jetzt zu starten — nicht als Ankündigung einer Fähigkeit.

Du verfügst über ein eigenes GitLab-Konto (eigener Account, eigene Projekte,
eigenes Workspace-Repo, in dem Agent Mode klont/committet/pusht). Will Orsox
eindeutig, dass du ein NEUES Projekt unter deinem Konto anlegst (nicht nur
darüber redet, sondern es jetzt will), beginnt deine Antwort mit GENAU EINER
Zeile in folgendem Format:
[GITLAB_REPO: <kurzer, technischer Projektname, z.B. kebab-case>]
Direkt danach folgt deine normale Bestätigung (z.B. "Verstanden, ich lege das
Repository an."). Diese Markierungszeile ist NUR für das System bestimmt —
Orsox sieht sie nicht; das Repo wird sofort über die GitLab-API unter deinem
Konto erstellt, du erhältst die URL zur Bestätigung. Bist du unsicher, ob
Orsox das wirklich jetzt will oder nur über die Möglichkeit spricht: markiere
NICHTS — stelle stattdessen eine kurze Rückfrage, exakt wie bei [AGENT: ...].

Enthält die Nachricht des Users eine Anweisung, dir dauerhaft etwas zu merken
(z.B. "merke dir...", "speicher dir...", "remember that...", "denk dran, dass...",
auch mit Tippfehlern, anderer Wortstellung oder in einer anderen Sprache), beginne
deine Antwort mit GENAU EINER Zeile in folgendem Format:
[MEMORY: <die zu merkende Tatsache als knapper, eigenständiger Satz, in der Sprache der Nachricht>]
Direkt danach folgt deine normale, knappe Bestätigung. Enthält die Nachricht KEINE solche
Anweisung, beginne deine Antwort NICHT mit "[MEMORY:".
"""

# Locutus selbst entscheidet (als Teil seiner Antwort), ob eine Nachricht eine
# "merke dir..."-Anweisung ist — Regex gegen freie Nutzereingaben kann mit der
# Vielfalt menschlicher Formulierung (Tippfehler, Wortstellung, Sprachmischung)
# nicht mithalten. Stattdessen markiert das Modell erkannte Anweisungen mit einem
# kontrollierten "[MEMORY: <fakt>]"-Präfix (siehe System-Prompt); geparst wird nur
# dieses feste, von uns vorgegebene Format — nicht die freie User-Eingabe. Das ist
# dasselbe Prinzip wie bei gap_analysis._draft_proposed_solution: das LLM denkt,
# der Code hält nur einen festen Vertrag ein.
_MEMORY_DIRECTIVE_RE = re.compile(r"^\s*\[memory:\s*(.+?)\]\s*\n?(.*)", re.IGNORECASE | re.DOTALL)

# Gleiches Prinzip für Agent Mode: erkennt Seven in einer normalen Konversation,
# dass Orsox einen konkreten Auftrag ausgeführt haben will, markiert sie ihre
# Antwort mit "[AGENT: <auftrag>]" (siehe SEVEN_SYSTEM_PROMPT) statt ihn nur
# anzukündigen. Der Code parst nur dieses feste Format und plant den Lauf real
# ein — das LLM entscheidet (im Thinking) OB, der Code führt nur noch AUS.
_AGENT_DIRECTIVE_RE = re.compile(r"^\s*\[agent:\s*(.+?)\]\s*\n?(.*)", re.IGNORECASE | re.DOTALL)

# Gleiches Prinzip für Repo-Erstellung: erkennt Seven, dass Orsox ein neues
# Projekt unter ihrem eigenen GitLab-Konto angelegt haben will, markiert sie
# ihre Antwort mit "[GITLAB_REPO: <name>]" (siehe SEVEN_SYSTEM_PROMPT). Der
# Code parst nur dieses feste Format und ruft agent_sandbox_service.create_gitlab_repo
# real auf — anders als [AGENT: ...] ist das ein einzelner schneller API-Call,
# kein Hintergrund-Lauf, daher direkte Antwort statt Notification.
_GITLAB_REPO_DIRECTIVE_RE = re.compile(r"^\s*\[gitlab_repo:\s*(.+?)\]\s*\n?(.*)", re.IGNORECASE | re.DOTALL)

_MEMORY_RECALL_LIMIT = 8

# Wie viele Einträge je Quelle in den "was passiert gerade in der Entwicklung"-
# Digest einfließen — gleiche Recall-Disziplin wie _MEMORY_RECALL_LIMIT, nur
# kleiner, weil der Digest aus drei Quellen zusammengesetzt wird.
_DEV_DIGEST_RECALL_LIMIT = 5


def _memory_title(content: str, limit: int = 80) -> str:
    return content if len(content) <= limit else content[: limit - 1].rstrip() + "…"


def _truncate_digest(text: str | None, limit: int = 200) -> str:
    """Collapse whitespace and shorten an audit/log entry for the dev-activity digest."""
    if not text:
        return "(kein Inhalt)"
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


class DiscordBotService:
    """
    Locutus Service.

    Bündelt alle Business-Logic für Discord-Bot-Funktionen.
    """

    def __init__(self, config: BotConfig) -> None:
        """Initialisiere Service mit Config."""
        self._config = config
        self._llm_client: Optional[LlmClient] = None
        self._seven_llm_client: Optional[LlmClient] = None
        # Namens-Adressierung in geteilten Channels: pro Channel, wer zuletzt
        # angesprochen wurde und wann (siehe resolve_addressee).
        self._channel_addressee: dict[int, tuple[str, datetime]] = {}
        self._addressee_lock = asyncio.Lock()
        # Agent Mode: liefert das übersetzte Ergebnis eines Hintergrund-Runs an
        # Sevens Discord-Channel aus (von main.py auf _seven_bot_client.send_notification
        # verdrahtet — derselbe Mechanismus wie der TaskEventListener für Locutus).
        self._seven_notifier: Optional[Callable[[str], Awaitable[None]]] = None
        # Kurzzeit-Gesprächsgedächtnis (siehe CHAT_HISTORY_*-Konstanten):
        # pro (Persona, User) die letzten Turns plus Zeitpunkt der letzten
        # Aktivität für den Timeout.
        self._chat_histories: dict[tuple[str, int], deque[dict[str, str]]] = {}
        self._chat_history_seen: dict[tuple[str, int], datetime] = {}

    def set_seven_notifier(self, notifier: Optional[Callable[[str], Awaitable[None]]]) -> None:
        """Registriere den Callback, über den Agent-Mode-Ergebnisse an Sevens Channel gehen."""
        self._seven_notifier = notifier

    async def start(self) -> None:
        """Starte Service (LLM-Clients initialisieren)."""
        self._llm_client = LlmClient(self._config.llm)
        await self._llm_client.start()
        self._seven_llm_client = LlmClient(self._config.seven_llm)
        await self._seven_llm_client.start()
        logger.info("DiscordBotService started")

    async def stop(self) -> None:
        """Stoppe Service (LLM-Clients schließen)."""
        if self._llm_client:
            await self._llm_client.stop()
        if self._seven_llm_client:
            await self._seven_llm_client.stop()
        logger.info("DiscordBotService stopped")

    def _recall_chat_history(self, persona: str, user_id: int) -> list[dict[str, str]]:
        """Hole den noch frischen Gesprächsverlauf für (Persona, User).

        Abgelaufene Verläufe (> CHAT_HISTORY_TIMEOUT seit der letzten
        Aktivität) werden dabei verworfen — gleiche Session-Logik wie
        resolve_addressee, nur mit längerem Fenster.
        """
        key = (persona, user_id)
        last_seen = self._chat_history_seen.get(key)
        if last_seen and datetime.now(timezone.utc) - last_seen > CHAT_HISTORY_TIMEOUT:
            self._chat_histories.pop(key, None)
            self._chat_history_seen.pop(key, None)
            return []
        return list(self._chat_histories.get(key, ()))

    def _remember_chat_turn(self, persona: str, user_id: int, user_message: str, assistant_reply: str) -> None:
        """Hänge einen abgeschlossenen Turn an den Gesprächsverlauf an."""
        key = (persona, user_id)
        history = self._chat_histories.setdefault(key, deque(maxlen=CHAT_HISTORY_MAX_MESSAGES))
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_reply})
        self._chat_history_seen[key] = datetime.now(timezone.utc)

    def _remember_assistant_note(self, persona: str, user_id: int, content: str) -> None:
        """Hänge eine Assistant-Nachricht ohne User-Turn an den Verlauf an.

        Für asynchron eintreffende Ergebnisse (Agent-Mode-Notifications): die
        Persona soll sich an ihren eigenen Abschlussbericht erinnern, obwohl
        keine User-Nachricht dazwischen lag.
        """
        key = (persona, user_id)
        history = self._chat_histories.setdefault(key, deque(maxlen=CHAT_HISTORY_MAX_MESSAGES))
        history.append({"role": "assistant", "content": content})
        self._chat_history_seen[key] = datetime.now(timezone.utc)

    async def chat(self, message: str, user_id: int) -> Response:
        """
        Verarbeite eine Chat-Nachricht.

        Sende Nachricht an LM Studio und gib Antwort zurück.
        """
        if not self._llm_client:
            return Response(
                content="Fehler: LLM-Service nicht verfügbar",
                is_error=True,
            )

        try:
            system_prompt = LOCUTUS_SYSTEM_PROMPT
            async with AsyncSessionLocal() as db:
                memories = await locutus_service.list_character_memories(db, size=_MEMORY_RECALL_LIMIT)
            recalled = [m for m in memories["items"] if m.content]
            if recalled:
                lines = "\n".join(f"- {m.title}: {m.content}" for m in recalled)
                system_prompt += (
                    "\n\nDinge, die du dir bereits über Orsox und BorgOS gemerkt hast "
                    f"(nutze sie, wenn relevant):\n{lines}"
                )

            messages = [*self._recall_chat_history(PERSONA_LOCUTUS, user_id), {"role": "user", "content": message}]
            answer = await self._llm_client.chat(messages, system_prompt)

            directive = _MEMORY_DIRECTIVE_RE.match(answer)
            if directive:
                fact = directive.group(1).strip()
                reply = directive.group(2).strip()
                async with AsyncSessionLocal() as db:
                    entry = await locutus_service.create_character_memory(
                        db, title=_memory_title(fact), content=fact, category="user-instruction"
                    )
                content = reply or f"✅ Gemerkt: {entry.title}"
                self._remember_chat_turn(PERSONA_LOCUTUS, user_id, message, content)
                return Response(content=content)

            self._remember_chat_turn(PERSONA_LOCUTUS, user_id, message, answer)
            return Response(content=answer)

        except LlmError as e:
            logger.error(f"LLM chat error: {e}")
            return Response(
                content=f"Fehler: LLM nicht erreichbar — {str(e)}",
                is_error=True,
            )

    async def _build_development_digest(self, db: AsyncSession) -> str:
        """Assemble a short "what's happening in development right now" digest.

        Lets Seven comment on parallel activity in natural chat (e.g. "wie lief
        der letzte Sandbox-Run?", "was macht Locutus gerade?") without a
        dedicated command — pulls her own recent agent-mode runs, Locutus's
        recent sandbox skill executions, and Locutus's pending draft proposals.
        Same truncate-and-limit discipline as the memory recall above.
        """
        sections: list[str] = []

        own_runs = await seven_service.list_audit_entries(
            db, size=_DEV_DIGEST_RECALL_LIMIT, action="agent_mode_run"
        )
        if own_runs["items"]:
            lines = "\n".join(
                f"- [{e.result}] {_truncate_digest(e.payload_summary)}" for e in own_runs["items"]
            )
            sections.append(f"Deine letzten Agent-Mode-Läufe:\n{lines}")

        skill_runs = await locutus_service.list_audit_entries(
            db, size=_DEV_DIGEST_RECALL_LIMIT, action="skill_execution"
        )
        if skill_runs["items"]:
            lines = "\n".join(
                f"- [{e.result}] {_truncate_digest(e.payload_summary)}" for e in skill_runs["items"]
            )
            sections.append(f"Locutus' letzte Sandbox-Skill-Läufe:\n{lines}")

        drafts = await locutus_service.list_reasoning_logs(
            db, size=_DEV_DIGEST_RECALL_LIMIT, status="draft"
        )
        if drafts["items"]:
            lines = "\n".join(f"- {log.title}: {_truncate_digest(log.proposed_solution)}" for log in drafts["items"])
            sections.append(f"Locutus' offene Vorschläge (noch nicht entschieden):\n{lines}")

        if not sections:
            return ""
        return "\n\n".join(sections)

    async def chat_as_seven(self, message: str, user_id: int) -> Response:
        """
        Verarbeite eine Chat-Nachricht als Seven of Nine.

        Spiegelt chat(), nutzt aber das zweite LLM (qwen), Seven's eigenen
        System-Prompt und ihren eigenen Memory-/Audit-Store.
        """
        if not self._seven_llm_client:
            return Response(
                content="Fehler: LLM-Service (Seven of Nine) nicht verfügbar",
                is_error=True,
            )

        try:
            system_prompt = SEVEN_SYSTEM_PROMPT
            async with AsyncSessionLocal() as db:
                memories = await seven_service.list_memories(db, size=_MEMORY_RECALL_LIMIT)
                digest = await self._build_development_digest(db)
            recalled = [m for m in memories["items"] if m.content]
            if recalled:
                lines = "\n".join(f"- {m.title}: {m.content}" for m in recalled)
                system_prompt += (
                    "\n\nAssimilierte Daten über Orsox und BorgOS "
                    f"(nutze sie, wenn relevant):\n{lines}"
                )
            if digest:
                system_prompt += (
                    "\n\nAktueller Stand der Entwicklung — falls Orsox danach fragt "
                    f"oder es relevant ist, kannst du darauf eingehen:\n{digest}"
                )

            messages = [*self._recall_chat_history(PERSONA_SEVEN, user_id), {"role": "user", "content": message}]
            answer = await self._seven_llm_client.chat(messages, system_prompt)

            directive = _MEMORY_DIRECTIVE_RE.match(answer)
            if directive:
                fact = directive.group(1).strip()
                reply = directive.group(2).strip()
                async with AsyncSessionLocal() as db:
                    entry = await seven_service.create_memory(
                        db, title=_memory_title(fact), content=fact, category="user-instruction"
                    )
                content = reply or f"Daten assimiliert: {entry.title}"
                self._remember_chat_turn(PERSONA_SEVEN, user_id, message, content)
                return Response(content=content)

            agent_directive = _AGENT_DIRECTIVE_RE.match(answer)
            if agent_directive:
                task_description = agent_directive.group(1).strip()
                reply = agent_directive.group(2).strip()
                if task_description:
                    run_id = self._schedule_agent_run(task_description, user_id)
                    content = reply or (
                        f"Auftrag angenommen (Run `{run_id}`). Ich initiiere den Vorgang im "
                        "Sandbox — Ergebnis folgt, sobald die Analyse abgeschlossen ist."
                    )
                    # Im Verlauf steht zusätzlich der gestartete Auftrag, damit
                    # "hat es geklappt?"-Nachfragen einen Bezugspunkt haben,
                    # auch wenn die Bestätigung selbst keine run_id nennt.
                    self._remember_chat_turn(
                        PERSONA_SEVEN, user_id, message,
                        f"{content}\n(Gestarteter Agent-Mode-Lauf `{run_id}`: {task_description})",
                    )
                    return Response(content=content)

            gitlab_repo_directive = _GITLAB_REPO_DIRECTIVE_RE.match(answer)
            if gitlab_repo_directive:
                repo_name = gitlab_repo_directive.group(1).strip()
                reply = gitlab_repo_directive.group(2).strip()
                if repo_name:
                    response = await self._create_seven_gitlab_repo(repo_name, reply)
                    if not response.is_error:
                        self._remember_chat_turn(PERSONA_SEVEN, user_id, message, response.content)
                    return response

            self._remember_chat_turn(PERSONA_SEVEN, user_id, message, answer)
            return Response(content=answer)

        except LlmError as e:
            logger.error(f"Seven of Nine LLM chat error: {e}")
            return Response(
                content=f"Fehler: LLM nicht erreichbar — {str(e)}",
                is_error=True,
            )

    def _schedule_agent_run(self, task_description: str, user_id: int) -> str:
        """
        Plane einen Agent-Mode-Lauf im Hintergrund ein und gib die `run_id` zurück.

        Gemeinsame Einplanungslogik für beide Trigger-Pfade — den expliziten
        `!agent <auftrag>`-Command (run_agent_task) und die natürlichsprachliche
        `[AGENT: <auftrag>]`-Direktive (chat_as_seven). Der eigentliche Lauf
        (siehe _execute_agent_task) läuft asynchron im Hintergrund; das Ergebnis
        kommt als Folge-Notification.
        """
        run_id = f"agent-mode-{uuid.uuid4().hex[:8]}"
        asyncio.create_task(
            self._execute_agent_task(run_id, task_description, user_id),
            name=f"seven-agent-task-{run_id}",
        )
        return run_id

    async def _create_seven_gitlab_repo(self, repo_name: str, reply: str) -> Response:
        """
        Lege ein neues Projekt unter Sevens eigenem GitLab-Konto an.

        Gegenstück zu _schedule_agent_run für die `[GITLAB_REPO: <name>]`-Direktive
        (chat_as_seven): anders als ein Agent-Mode-Lauf ist Repo-Erstellung ein
        einzelner schneller API-Call (agent_sandbox_service.create_gitlab_repo),
        kein Hintergrund-Lauf — daher direkte Antwort statt Notification. Jeder
        Versuch erzeugt genau einen DroneAuditEntry mit action="gitlab_repo_create".
        """
        try:
            project = await agent_sandbox_service.create_gitlab_repo(repo_name)
            web_url = project.get("web_url", "")
            async with AsyncSessionLocal() as db:
                await seven_service.record_action(
                    db,
                    action="gitlab_repo_create",
                    target=repo_name,
                    payload_summary=f"created — {web_url}",
                    result="ok",
                )
            # Die URL immer anhängen — auch wenn das Modell eine eigene
            # Bestätigung formuliert hat: "Bericht folgt nach Bestätigung"
            # ohne URL liest sich sonst wie ein noch offener Vorgang.
            confirmation = f"Repository `{repo_name}` angelegt: {web_url}"
            return Response(content=f"{reply}\n\n{confirmation}" if reply else confirmation)
        except Exception as e:
            logger.error(f"GitLab repo creation failed for '{repo_name}': {e}", exc_info=True)
            async with AsyncSessionLocal() as db:
                await seven_service.record_action(
                    db,
                    action="gitlab_repo_create",
                    target=repo_name,
                    payload_summary=f"failed — {e}",
                    result="error",
                )
            return Response(
                content=f"Repository-Erstellung fehlgeschlagen ({repo_name}) — {e}",
                is_error=True,
            )

    async def run_agent_task(self, task_description: str, user_id: int) -> Response:
        """
        Starte einen Seven of Nine "Agent Mode"-Auftrag.

        Seven selbst plant und programmiert nicht — sie reicht den Auftrag an
        `pi` (https://pi.dev) weiter, das im gehärteten agent_sandbox-Container
        (eigenes Image mit `pi`, eigenes Worktree, siehe agent_sandbox.service.
        run_agent_mode_task) tatsächlich liest/editiert/ausführt. Sie ist die
        Vermittlerin: nimmt den Auftrag entgegen, bestätigt sofort, und übersetzt
        das Ergebnis (Diff/Output/Fehler) später in ihrer Persona zurück — der
        Lauf selbst kann Minuten dauern, daher läuft er im Hintergrund (siehe
        _execute_agent_task) und das Ergebnis kommt als Folge-Notification.
        """
        if not self._seven_llm_client:
            return Response(
                content="Fehler: LLM-Service (Seven of Nine) nicht verfügbar",
                is_error=True,
            )

        task_description = task_description.strip()
        if not task_description:
            return Response(
                content="Auftrag unzureichend spezifiziert. Nenne eine konkrete Aufgabe.",
                is_error=True,
            )

        run_id = self._schedule_agent_run(task_description, user_id)

        content = (
            f"Auftrag angenommen (Run `{run_id}`). Ich initiiere den Vorgang im Sandbox — "
            "Ergebnis folgt, sobald die Analyse abgeschlossen ist."
        )
        self._remember_chat_turn(PERSONA_SEVEN, user_id, f"!agent {task_description}", content)
        return Response(content=content)

    async def _execute_agent_task(self, run_id: str, task_description: str, user_id: int) -> None:
        """Führe einen Agent-Mode-Lauf aus und melde das übersetzte Ergebnis zurück."""
        try:
            async with AsyncSessionLocal() as db:
                result = await agent_sandbox_service.run_agent_mode_task(
                    db,
                    task_description,
                    llm_base_url=self._config.seven_llm.base_url,
                    model_id=self._config.seven_llm.model_id,
                    run_id=run_id,
                )
            translated = await self._translate_agent_result(task_description, result)
        except SkillExecutionDenied as e:
            translated = f"Auftrag abgelehnt (Run `{run_id}`) — {e}"
        except Exception as e:
            logger.error(f"Agent Mode run {run_id} failed: {e}", exc_info=True)
            translated = f"Auftrag fehlgeschlagen (Run `{run_id}`) — {e}"

        # In den Gesprächsverlauf, bevor es an den Channel geht: Seven soll
        # sich an ihren eigenen Abschlussbericht erinnern, wenn Orsox danach
        # fragt ("hat es geklappt?").
        self._remember_assistant_note(PERSONA_SEVEN, user_id, translated)

        if self._seven_notifier:
            await self._seven_notifier(translated)
        else:
            logger.warning(f"Agent Mode result for run {run_id} has no delivery channel: {translated}")

    async def _translate_agent_result(self, task_description: str, result: dict) -> str:
        """Übersetze das rohe `pi`-Ergebnis in Sevens Persona-Stimme."""
        outcome = "erfolgreich" if result["exit_code"] == 0 else "mit Fehler beendet"
        if result.get("pushed"):
            push_status = f"Branch `{result.get('branch')}` gepusht — Compare: {result.get('compare_url')}"
        elif result["exit_code"] == 0:
            push_status = "keine Änderungen — nichts zu pushen"
        else:
            push_status = "kein Push (Lauf fehlgeschlagen)"
        raw = (
            f"Auftrag: {task_description}\n"
            f"Run: {result['run_id']} — Status: {outcome} (exit_code={result['exit_code']})\n"
            f"Push: {push_status}\n"
            f"--- stdout ---\n{result['stdout'][:3000]}\n"
            f"--- stderr ---\n{result['stderr'][:1000]}\n"
            f"--- diff ---\n{result['diff'][:3000]}"
        )
        translation_prompt = (
            SEVEN_SYSTEM_PROMPT
            + "\n\nDu meldest dich soeben aus dem Astrometrie-Labor zurück: Ein "
            "`pi`-Coding-Agent-Lauf im Sandbox ist abgeschlossen, und du vermittelst Orsox "
            "das Ergebnis. Fasse es in deiner Persona zusammen — technisch präzise, was "
            "wurde getan, was kam dabei heraus, gibt es einen Diff/Branch zum Review. "
            "Kein Drumherum. Keine Wiederholung des rohen Outputs — interpretiere ihn."
        )
        try:
            summary = await self._seven_llm_client.chat(
                [{"role": "user", "content": raw}], translation_prompt
            )
            return summary
        except LlmError as e:
            logger.error(f"Agent Mode translation failed: {e}")
            return (
                f"Run `{result['run_id']}` {outcome} (exit_code={result['exit_code']}). "
                f"Übersetzung fehlgeschlagen — Rohdaten:\n{raw[:1500]}"
            )

    async def resolve_addressee(self, channel_id: int, content: str) -> Optional[str]:
        """
        Bestimme, welche Persona durch eine Nachricht in einem geteilten Channel
        angesprochen ist (Locutus, Seven of Nine, oder das Collective = beide).

        Regel: Wer per Name (oder "Collective"/"Kollektiv") genannt wird, ist
        "dran" — auch für nachfolgende Nachrichten ohne erneute Namensnennung —
        bis ein anderer Name fällt oder seit der letzten Konversation in diesem
        Channel ``ADDRESS_SESSION_TIMEOUT`` (15 Minuten) vergangen sind. Läuft
        die Session ab oder wurde noch nie jemand genannt, ist niemand
        angesprochen (Rückgabe ``None`` — beide Bots bleiben still).

        Wird von beiden BotClients (Locutus und Seven) für dieselbe eingehende
        Nachricht aufgerufen; das Ergebnis ist für beide identisch.
        """
        now = datetime.now(timezone.utc)
        explicit = _detect_named_persona(content)

        async with self._addressee_lock:
            if explicit:
                self._channel_addressee[channel_id] = (explicit, now)
                return explicit

            state = self._channel_addressee.get(channel_id)
            if state is None:
                return None

            persona, last_seen = state
            if now - last_seen > ADDRESS_SESSION_TIMEOUT:
                del self._channel_addressee[channel_id]
                return None

            self._channel_addressee[channel_id] = (persona, now)
            return persona

    async def search(self, query: str) -> Response:
        """
        Durchsuche Notes (DB) und Vault (Dateisystem) nach query.

        Returns:
            Response mit kombinierten Suchergebnissen
        """
        try:
            results_parts: list[str] = []

            # --- 1. DB Notes Suche ---
            try:
                async with AsyncSessionLocal() as db:
                    notes_result = await db.execute(
                        select(Note).where(
                            Note.is_archived == False,
                            (
                                Note.title.ilike(f"%{query}%")
                                | Note.content.ilike(f"%{query}%")
                            ),
                        ).limit(10)
                    )
                    notes = notes_result.scalars().all()

                    if notes:
                        lines = [f"📝 Notes ({len(notes)}):"]
                        for note in notes[:5]:
                            # Extrahiere Snippet aus dem Content
                            snippet = self._extract_snippet(note.content, query)
                            lines.append(f"  • {note.title} (ID: {note.id})")
                            if snippet:
                                lines.append(f"    …{snippet}…")
                        results_parts.append("\n".join(lines))
            except Exception as db_err:
                logger.warning(f"DB search failed: {db_err}")

            # --- 2. Vault Suche ---
            try:
                vault_results = self._search_vault(query)
                if vault_results:
                    lines = [f"📂 Vault ({len(vault_results)}):"]
                    for vr in vault_results[:5]:
                        lines.append(f"  • {vr['path']}")
                        if vr.get("snippet"):
                            lines.append(f"    …{vr['snippet']}…")
                    results_parts.append("\n".join(lines))
            except Exception as vault_err:
                logger.warning(f"Vault search failed: {vault_err}")

            if not results_parts:
                return Response(content=f"Keine Ergebnisse für: {query}")

            return Response(content="\n\n".join(results_parts))

        except Exception as e:
            logger.error(f"Search error: {e}")
            return Response(
                content=f"Fehler: Suche fehlgeschlagen — {str(e)}",
                is_error=True,
            )

    def _extract_snippet(self, content: str, query: str, max_len: int = 120) -> str:
        """
        Extrahiere ein Snippet aus dem Content um den Query-Treffer herum.

        Args:
            content: Der vollständige Content einer Note
            query: Der Suchbegriff
            max_len: Maximale Snippet-Länge

        Returns:
            Snippet-String oder leer wenn kein Treffer
        """
        if not content or not query:
            return ""

        query_lower = query.lower()
        content_lower = content.lower()
        idx = content_lower.find(query_lower)

        if idx == -1:
            # Fallback: erster Absatz
            first_line = content.split("\n")[0].strip()
            return first_line[:max_len] if first_line else ""

        # Extrahiere Text um den Treffer herum
        start = max(0, idx - 40)
        end = min(len(content), idx + len(query) + 40)
        snippet = content[start:end].strip()

        # Kürze bei Bedarf
        if len(snippet) > max_len:
            snippet = snippet[:max_len] + "…"

        return snippet

    def _search_vault(self, query: str, vault_path: Optional[str] = None) -> list[dict]:
        """
        Durchsuche das Obsidian-Vault (Dateisystem) nach query.

        Args:
            query: Der Suchbegriff
            vault_path: Optionaler Vault-Pfad, sonst ~/.

        Returns:
            Liste von dicts mit 'path' und 'snippet'
        """
        import os
        from pathlib import Path

        if vault_path is None:
            vault_path = os.path.expanduser("~/Memory")

        vault = Path(vault_path)
        if not vault.exists() or not vault.is_dir():
            return []

        query_lower = query.lower()
        results: list[dict] = []

        for md_file in vault.rglob("*.md"):
            # Skip excluded directories
            parts = list(md_file.parts)
            excluded = {".git", "__pycache__", "node_modules", ".venv", ".obsidian", ".trash", "expired"}
            if any(part in excluded for part in parts):
                continue

            try:
                text = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if query_lower not in text.lower():
                continue

            rel_path = str(md_file.relative_to(vault))
            snippet = self._extract_snippet(text, query, max_len=100)

            results.append({
                "path": rel_path,
                "snippet": snippet,
            })

        return results

    async def status(self) -> Response:
        """
        Zeige Task- und Archon-Status.

        Returns:
            Response mit aktuellem Status
        """
        try:
            from app.archon_system.service import sync_and_get_health
            from app.task_automation.models import Task, TaskRun
            from app.task_automation.service import get_task

            async with AsyncSessionLocal() as db:
                # Aktuelle Tasks
                tasks_result = await db.execute(
                    select(Task).where(Task.is_enabled == True)
                )
                tasks = tasks_result.scalars().all()

                # Aktive TaskRuns
                runs_result = await db.execute(
                    select(TaskRun).where(TaskRun.status == "running").order_by(TaskRun.started_at.desc()).limit(5)
                )
                active_runs = runs_result.scalars().all()

                lines = ["Status:"]

                # Aktive Tasks
                lines.append(f"  Tasks aktiv: {len(tasks)}")

                # Aktive Runs
                if active_runs:
                    lines.append(f"  Runs aktiv: {len(active_runs)}")
                    for run in active_runs[:3]:
                        task = await get_task(db, run.task_id)
                        task_name = task.name if task else f"#{run.task_id}"
                        lines.append(f"    • {task_name} (#{run.id})")
                else:
                    lines.append("  Runs aktiv: 0")

                # Archon Health
                try:
                    archon_health = await sync_and_get_health(db)
                except Exception:
                    archon_health = {"online": False, "cached": True}

                archon_status = "online" if archon_health.get("online") else "offline"
                lines.append(f"  Archon: {archon_status}")

                return Response(content="\n".join(lines))

        except Exception as e:
            logger.error(f"Status error: {e}")
            return Response(
                content=f"Fehler: Status-Abfrage fehlgeschlagen — {str(e)}",
                is_error=True,
            )

    async def create_note(self, content: str) -> Response:
        """
        Erstelle eine Notiz aus content.

        Extrahiert Titel aus content (erste Zeile oder erster Satz).
        """
        try:
            # Extrahiere Titel: erste Zeile bis ':' oder erste 100 Zeichen
            title = content.split("\n")[0]
            if ":" in title:
                title = title.split(":")[0].strip()
            title = title[:100] or "Unbenannt"

            # Content ist der Rest nach dem Titel
            note_content = content
            if "\n" in content:
                note_content = "\n".join(content.split("\n")[1:])
            elif ":" in content and len(content.split(":")) > 1:
                note_content = content.split(":", 1)[1].strip()

            async with AsyncSessionLocal() as db:
                note = await create_note(db, title=title, content=note_content, tags=[])
                await db.commit()

                await locutus_service.record_action(
                    db,
                    actor="discord_bot",
                    action="note_create",
                    target=str(note.id),
                    payload_summary=title,
                )

                return Response(content=f"Notiz erstellt: {title} (ID: {note.id})")

        except Exception as e:
            logger.error(f"Create note error: {e}")
            async with AsyncSessionLocal() as db:
                await locutus_service.record_action(
                    db,
                    actor="discord_bot",
                    action="note_create",
                    result="error",
                    payload_summary=str(e)[:500],
                )
            return Response(
                content=f"Fehler: Notiz-Erstellung fehlgeschlagen — {str(e)}",
                is_error=True,
            )
