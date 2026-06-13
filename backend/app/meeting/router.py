"""
FastAPI router for the conference room.

JWT-guarded (like every other module router); module-level singleton wired in
main.py via ``set_meeting_service`` — same pattern as discord_bot/router.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.router import get_current_user

from .orchestrator import MeetingService, MeetingSession
from .schemas import (
    MeetingMessageIn,
    MeetingSessionOut,
    MeetingTurnOut,
    PersonaOut,
    StartMeetingIn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meeting", tags=["meeting"])

_meeting_service: MeetingService | None = None


def set_meeting_service(service: MeetingService) -> None:
    """Set the global meeting service reference (called from main.py)."""
    global _meeting_service
    _meeting_service = service


def get_meeting_service() -> MeetingService:
    if _meeting_service is None:
        raise HTTPException(status_code=503, detail="Meeting service not initialized")
    return _meeting_service


def _to_out(session: MeetingSession) -> MeetingSessionOut:
    return MeetingSessionOut(
        id=session.id,
        theme=session.theme,
        rounds_total=session.rounds_total,
        rounds_done=session.rounds_done,
        status=session.status,
        speaking=session.speaking,
        error=session.error,
        transcript=[
            MeetingTurnOut(
                speaker=t.speaker,
                display_name=t.display_name,
                content=t.content,
                ts=t.ts,
            )
            for t in session.transcript
        ],
    )


@router.get("/personas", response_model=list[PersonaOut])
async def list_personas(
    _user=Depends(get_current_user),
    service: MeetingService = Depends(get_meeting_service),
):
    """List the participants at the table (for the frontend to render stations)."""
    return [
        PersonaOut(key=p.key, display_name=p.display_name, color=p.color)
        for p in service.personas
    ]


@router.post("/sessions", response_model=MeetingSessionOut)
async def start_meeting(
    body: StartMeetingIn,
    _user=Depends(get_current_user),
    service: MeetingService = Depends(get_meeting_service),
):
    """Start a meeting on a theme for ``rounds`` round-robin rounds."""
    session = service.start_meeting(body.theme, body.rounds)
    return _to_out(session)


@router.get("/sessions/{session_id}", response_model=MeetingSessionOut)
async def get_session(
    session_id: str,
    _user=Depends(get_current_user),
    service: MeetingService = Depends(get_meeting_service),
):
    """Poll the current snapshot of a meeting (transcript + speaker + status)."""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _to_out(session)


@router.post("/sessions/{session_id}/message", response_model=MeetingSessionOut)
async def send_message(
    session_id: str,
    body: MeetingMessageIn,
    _user=Depends(get_current_user),
    service: MeetingService = Depends(get_meeting_service),
):
    """Inject an Orsox follow-up and run another round budget on the same room."""
    try:
        session = service.add_message(session_id, body.message, body.rounds)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if session is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _to_out(session)
