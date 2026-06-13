"""Tests for the Meeting (conference room) module.

Never touches LM Studio — LlmClient.chat is stubbed (mirrors the "tests never
touch Langfuse" rule).
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.discord_bot.config import BotConfig
from app.discord_bot.llm import LlmClient
from app.main import app
from app.meeting import router as meeting_router
from app.meeting.orchestrator import (
    STATUS_DONE,
    STATUS_RUNNING,
    SPEAKER_ORSOX,
    MeetingService,
)


async def _fake_chat(self, messages, system_prompt):
    """Canned per-persona reply derived from the turn instruction.

    Seven prefixes a forbidden directive marker so we can assert it is stripped.
    """
    user = messages[0]["content"]
    if "Du bist Seven of Nine" in user:
        return "[AGENT: irgendwas]\nAnalyse: Wahrscheinlichkeit von Erfolg hoch."
    return "Wir haben die Lage bewertet."


@pytest.fixture
def stub_llm(monkeypatch):
    monkeypatch.setattr(LlmClient, "chat", _fake_chat)


async def _build_service() -> MeetingService:
    service = MeetingService(BotConfig.from_env_locutus())
    await service.start()
    return service


async def _await_done(service: MeetingService, session_id: str, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        session = service.get_session(session_id)
        if session and session.status != STATUS_RUNNING:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("meeting did not finish in time")


async def test_round_robin_order_and_budget(stub_llm):
    service = await _build_service()
    session = service.start_meeting("Sollen wir peer_sync refactoren?", rounds=2)
    assert session.status == STATUS_RUNNING

    await _await_done(service, session.id)
    session = service.get_session(session.id)

    assert session.status == STATUS_DONE
    assert session.rounds_done == 2
    assert session.speaking is None

    # Seeded Orsox turn + 2 rounds x 2 personas.
    speakers = [t.speaker for t in session.transcript]
    assert speakers == [SPEAKER_ORSOX, "locutus", "seven", "locutus", "seven"]

    await service.stop()


async def test_directive_markers_stripped(stub_llm):
    service = await _build_service()
    session = service.start_meeting("Thema", rounds=1)
    await _await_done(service, session.id)
    session = service.get_session(session.id)

    seven_turn = next(t for t in session.transcript if t.speaker == "seven")
    assert not seven_turn.content.startswith("[AGENT:")
    assert "Analyse" in seven_turn.content

    await service.stop()


async def test_followup_extends_same_transcript(stub_llm):
    service = await _build_service()
    session = service.start_meeting("Thema", rounds=1)
    await _await_done(service, session.id)

    extended = service.add_message(session.id, "Und der Sicherheitsaspekt?", rounds=1)
    assert extended is not None
    await _await_done(service, session.id)
    session = service.get_session(session.id)

    # 1 round + Orsox follow-up + 1 more round.
    speakers = [t.speaker for t in session.transcript]
    assert speakers == [
        SPEAKER_ORSOX, "locutus", "seven",
        SPEAKER_ORSOX, "locutus", "seven",
    ]
    assert session.rounds_done == 2
    assert session.rounds_total == 2

    await service.stop()


# --- Router ---

def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient) -> dict[str, str]:
    login = await client.post("/api/auth/token", data={"username": "borg", "password": "borgborg"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_personas_endpoint(stub_llm):
    service = await _build_service()
    meeting_router.set_meeting_service(service)
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/meeting/personas", headers=headers)
        assert resp.status_code == 200
        keys = [p["key"] for p in resp.json()]
        assert keys == ["locutus", "seven"]
    await service.stop()


async def test_start_and_poll_session(stub_llm):
    service = await _build_service()
    meeting_router.set_meeting_service(service)
    async with _client() as client:
        headers = await _login(client)
        resp = await client.post(
            "/api/meeting/sessions", json={"theme": "Thema", "rounds": 1}, headers=headers
        )
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        await _await_done(service, session_id)
        poll = await client.get(f"/api/meeting/sessions/{session_id}", headers=headers)
        assert poll.status_code == 200
        body = poll.json()
        assert body["status"] == STATUS_DONE
        assert len(body["transcript"]) == 3
    await service.stop()


async def test_session_requires_auth(stub_llm):
    async with _client() as client:
        resp = await client.get("/api/meeting/sessions/nope")
        assert resp.status_code == 401
