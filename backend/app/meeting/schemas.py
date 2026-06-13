"""Schemas for the Meeting (conference room) module."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PersonaOut(BaseModel):
    """A participant station for the frontend to render."""

    key: str
    display_name: str
    color: str


class MeetingTurnOut(BaseModel):
    """One utterance in the transcript."""

    speaker: str
    display_name: str
    content: str
    ts: str


class MeetingSessionOut(BaseModel):
    """Poll snapshot of a conference room."""

    id: str
    theme: str
    rounds_total: int
    rounds_done: int
    status: str
    speaking: Optional[str] = None
    error: Optional[str] = None
    transcript: list[MeetingTurnOut]


class StartMeetingIn(BaseModel):
    theme: str = Field(min_length=1)
    rounds: int = Field(default=3, ge=1, le=12)


class MeetingMessageIn(BaseModel):
    message: str = Field(min_length=1)
    rounds: int = Field(default=3, ge=1, le=12)
