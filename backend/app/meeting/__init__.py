"""
Meeting module — the BorgOS conference room.

Lets the personas (Locutus, Seven of Nine) hold a roundtable discussion on a
theme Orsox sets, taking turns round-robin for a chosen number of rounds. A
separate surface from the Discord bot, but reuses the same system prompts and
LM Studio clients. Meetings are ephemeral (in-memory) — a backend restart
clears them, mirroring the in-memory chat-history philosophy in
``discord_bot/service.py``.
"""
