"""
Locutus FastAPI-Router.

Stellt interne Endpoints für den Discord-Bot bereit.
Dient als Bridge zwischen Discord und BorgOS-Backend.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth.router import get_current_user
from app.auth.models import User

from .service import DiscordBotService
from .handlers import CommandHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locutus", tags=["locutus"])

# Global reference to the bot service — set by main.py during startup
_bot_service: DiscordBotService | None = None


def set_bot_service(service: DiscordBotService) -> None:
    """Set the global bot service reference (called from main.py)."""
    global _bot_service
    _bot_service = service


def get_bot_service() -> DiscordBotService:
    """Dependency: Liefert den DiscordBotService."""
    if _bot_service is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    return _bot_service


@router.get("/health")
async def health(
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Health-Check für Locutus."""
    return {"status": "ok", "service": "locutus"}


@router.post("/chat")
async def chat(
    message: str,
    user_id: int,
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Chat-Endpoint für Locutus."""
    response = await service.chat(message, user_id)
    return {"content": response.content, "is_error": response.is_error}


@router.post("/search")
async def search(
    query: str,
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Suche-Endpoint für Locutus."""
    response = await service.search(query)
    return {"content": response.content, "is_error": response.is_error}


@router.get("/status")
async def status(
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Status-Endpoint für Locutus."""
    response = await service.status()
    return {"content": response.content, "is_error": response.is_error}


@router.post("/note")
async def create_note(
    content: str,
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Notiz-Erstellen-Endpoint für Locutus."""
    response = await service.create_note(content)
    return {"content": response.content, "is_error": response.is_error}


@router.post("/dispatch")
async def dispatch(
    content: str,
    user_id: int,
    _user=Depends(get_current_user),
    service: DiscordBotService = Depends(get_bot_service),
):
    """Command-Dispatch-Endpoint für Locutus.
    
    Parst eine Nachricht als Command und dispatcht sie zum passenden Handler.
    """
    handler = CommandHandler(service=service)
    command = handler.parse(content, user_id, 0)  # channel_id=0 für API-Calls
    
    if command is None:
        return {"content": "Kein Command erkannt. Verwende !help für Hilfe.", "is_error": False}
    
    response = await handler.handle(command)
    return {"content": response.content, "is_error": response.is_error}
