"""Persona management module.

Stores persona (character) definitions in the database, replacing the previous
.env-only configuration. Each persona carries its own LLM settings, Discord bot
account config, system prompt text, and display metadata.

Consumers:
- discord_bot/service.py — loads LlmConfig + BotConfig from DB personas at startup
- meeting/personas.py — builds MeetingParticipant list dynamically from active personas
"""
