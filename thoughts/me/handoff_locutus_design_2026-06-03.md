---
date: 2026-06-03T16:13:53+0000
author: bernd
commit: df46e6b
branch: main
repository: borg
topic: "Discord-Bot-Integration Locutus — Kontext-Komprimierung"
tags: [handoff, discord-bot, locutus]
---

# Handoff: Locutus Discord-Bot Design abgeschlossen

## Was erledigt wurde

Das Design-Dokument für die Discord-Bot-Integration "Locutus" wurde vollständig erstellt und alle 5 Slices generiert.

**Design-Artifact:** `.rpiv/artifacts/designs/2026-06-03_16-13-53_discord-bot-locutus.md`

**Status:** Alle 5 Slices completed, 88 Tests bestanden (26 neue + 62 bestehende).

## Architektur-Entscheidungen (fest)

1. **In-process-Modul** — Bot läuft im FastAPI-Prozess, direkter SSE-Queue-Zugriff
2. **Message-basiert** — @-Erwähnungen + Prefix (`!`) als Trigger
3. **Name:** Locutus, **Persönlichkeit:** knapp & technisch
4. **Internal Auth Bypass** — Kein JWT-Overhead für Service-Aufrufe
5. **LM Studio Local Model** — mellum2-12b-a2.5b-instruct
6. **Alle Task-Events** melden (started, completed, failed)
7. **Kurze Fehlermeldungen** in Discord
8. **Environment Variable** für Config (`DISCORD_BOT_TOKEN`, etc.)
9. **Pure Unit Tests** für Command-Parsing und Handler

## Files (neu)

| File | Zeilen | Beschreibung |
|------|--------|--------------|
| `backend/app/discord_bot/__init__.py` | 16 | Package-Init |
| `backend/app/discord_bot/config.py` | 58 | BotConfig + LlmConfig (pydantic) |
| `backend/app/discord_bot/models.py` | 87 | Command, Response, TaskEvent, TaskNotification |
| `backend/app/discord_bot/handlers.py` | 175 | CommandHandler mit Parsing + 5 Handler |
| `backend/app/discord_bot/listener.py` | 99 | TaskEventListener (sse_queue Listener) |
| `backend/app/discord_bot/llm.py` | 109 | LlmClient (LM Studio HTTP-Client) |
| `backend/app/discord_bot/service.py` | 198 | DiscordBotService (chat, search, status, create_note) |
| `backend/app/discord_bot/router.py` | 113 | FastAPI-Router mit 6 Endpoints |
| `backend/tests/test_discord_bot.py` | 329 | 26 Unit-Tests |

## Files (modified)

| File | Beschreibung |
|------|--------------|
| `backend/app/config.py` | 7 neue Settings + `discord_bot_allowed_user_ids_list` Property |
| `backend/app/main.py` | Bot-Init/Shutdown in lifespan, Router-Integration |

## Was Locutus jetzt kann (Backend fertig)

- ✅ Command-Parsing (`!command`, `@Locutus command`)
- ✅ Notifications (SSE-Queue Listener, Task-Events)
- ✅ Status (aktive Tasks + Runs)
- ✅ Suche (DB-Notes-Suche)
- ✅ Notiz erstellen (mit Titel-Extraktion)
- ✅ Chat (LLM-Client für LM Studio, benötigt laufendes LM Studio)
- ✅ 6 API-Endpoints (`/api/locutus/*`)
- ✅ Lifecycle-Management (Init/Shutdown in lifespan)

## Was noch fehlt (nächste Schritte)

### 1. Discord-Client (discord.py)
- `discord.py` als Dependency hinzufügen
- Discord-Client-Modul erstellen (`discord_bot/client.py`)
- Message-Handler: Discord-Nachrichten → Command-Parsing → API-Call → Discord-Antwort
- Slash-Command-Registration (optional, message-basiert reicht)
- Notification-Callback: SSE-Event → Discord-Message senden

### 2. Integrationstests
- Integrationstests mit ASGITransport für Bot-Endpoints
- Mock-Tests für Discord-Client

### 3. Docker-Integration
- Bot als dritten Service in `docker-compose.yml` ODER In-process im Backend
- `DISCORD_BOT_TOKEN` als Secret/Env-Var
- Health-Check für Bot

### 4. Dokumentation
- `.env.example` um Discord-Bot Settings erweitern
- README-Eintrag für Locutus

## Test-Ergebnisse

```
88 passed, 4546 warnings in 50.17s
  - 26 neue Tests (test_discord_bot.py)
  - 62 bestehende Tests (test_api.py, test_archon_system.py, test_vault_graph.py)
```

## Nächster Schritt

**`/skill:implement`** — Den Design-Plan in Implementierung überführen.

Oder direkt weiter mit Discord-Client-Integration:
1. `pip install discord.py` (oder `uv add discord.py`)
2. `backend/app/discord_bot/client.py` erstellen
3. Discord-Client mit Bot-Token authentifizieren
4. Message-Handler implementieren
5. Notification-Callback mit Discord API verbinden

## Wichtige Hinweise

- SSE-Queue ist **single-consumer** — nur ein Consumer pro Event. Locutus liest direkt aus `sse_queue` (`scheduler.py:22`).
- Der `notification_callback` in `main.py` ist ein **Placeholder** — er loggt nur. Die eigentliche Discord-Nachricht muss noch implementiert werden.
- LM Studio muss laufen unter `http://localhost:1234` für Chat-Funktion.
- Bot ist **optional** — `DISCORD_BOT_ENABLED=false` (default) deaktiviert ihn komplett.
