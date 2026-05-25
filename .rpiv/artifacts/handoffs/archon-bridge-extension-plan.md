# Archon Bridge Extension Plan

## Ziel
Eine Pi-Extension soll Archon-Workflows asynchron überwachen und offene menschliche Rückfragen direkt in Pi anzeigen und beantworten helfen.

## Anforderungen
- Beobachtet Archon-Runs per **SSE-first**, Polling nur als Fallback.
- Behandelt nicht nur **Approval-Gates**, sondern auch:
  - freie Anfragen
  - Reviews
  - Feedback-Requests
  - generische pausierte Rückfragen
- Nutzt nur **beobachtete Run-IDs**.
- Wenn ein Workflow **aus Pi gestartet oder resumed** wird, wird der Run **automatisch registriert**.
- Antwortvorschläge können über ein **konfigurierbares Pi-Modell** erzeugt werden.
- Antworten werden **nicht automatisch abgeschickt**; User bestätigt/editiert zuerst.

## Empfohlene Architektur
### Module
- `connection`
  - SSE-Verbindung zu Archon
  - Reconnect / Heartbeat / Fallback auf Polling
- `watch-store`
  - beobachtete Run-IDs
  - Persistenz und Dedupe
- `run-discovery`
  - erkennt neu gestartete/resumte Archon-Workflows aus Pi
  - registriert Runs automatisch
- `run-resolver`
  - lädt Run-Details via Archon API
- `question-detector`
  - klassifiziert offene menschliche Aktionen:
    - `approval`
    - `review`
    - `question`
    - `feedback-request`
    - `unknown-paused`
- `artifact-inspector` (optional / später)
  - lädt referenzierte Review-/Plan-Artefakte für besseren Kontext
- `reply-assistant`
  - erzeugt mit konfigurierbarem Pi-Modell Antwortentwürfe
- `archon-api`
  - approve / reject / fetch run / ggf. reply
- `inbox-ui`
  - Widget / Overlay / Commands in Pi

## Pi-UI
### Commands
- `/archon-run ...`
- `/archon-continue ...`
- `/archon-watch <runId>`
- `/archon-unwatch <runId>`
- `/archon-inbox`
- `/archon-reply <runId>`
- `/archon-approve <runId>`
- `/archon-reject <runId>`
- `/archon-bridge-status`
- `/archon-bridge-model`

### UI-Elemente
- Footer-Status: Verbindung + Anzahl offener Anfragen
- Widget: offene Inbox-Einträge
- Dialog/Overlay: Details + Antwortbearbeitung

## Datenfluss
1. Pi startet/resumed Archon-Workflow.
2. Run wird automatisch in Watchlist eingetragen.
3. Archon meldet Pause/Nachfrage via SSE (oder Polling-Fallback).
4. Extension lädt Run-Details.
5. Extension klassifiziert Anfrage/Review/Approval.
6. Inbox-Eintrag wird in Pi angezeigt.
7. Optional: Modell erzeugt Antwortentwurf.
8. User bestätigt oder editiert.
9. Extension sendet Approve/Reject/Reply an Archon.
10. Run bleibt beobachtet bis terminaler Status erreicht ist.

## Technische Quellen
### Pi
- `docs/extensions.md`
- `docs/tui.md`
- `docs/models.md`
- Beispiele:
  - `examples/extensions/file-trigger.ts`
  - `examples/extensions/send-user-message.ts`
  - `examples/extensions/qna.ts`
  - `examples/extensions/preset.ts`

### Archon
- `packages/server/src/routes/api.ts`
- `packages/server/src/adapters/web/workflow-bridge.ts`
- `packages/docs-web/src/content/docs/guides/authoring-workflows.md`

## MVP
### Phase 1
- Watchlist
- automatische Registrierung bei Start/Continue
- SSE beobachten
- paused runs erkennen
- Approval + freie Reviews/Fragen anzeigen
- manuelles Approve/Reject/Reply

### Phase 2
- Antwortentwurf per konfigurierbarem Pi-Modell
- besserer Inbox-/Overlay-Flow
- Run-Details/Artefakte anzeigen

### Phase 3
- erweiterte Artefaktanalyse
- robustere Heuristiken für freie Nachfragen
- Multi-run UX verbessern
