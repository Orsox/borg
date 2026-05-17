#!/home/bernd/.claude/venv/bin/python3
"""FastEmbed wrapper — singleton model, batch embedding API."""
from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSIONS = 384

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        # Downloads ~22MB to ~/.cache/fastembed/ on first run
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Returns list of 384-dim float vectors."""
    return [v.tolist() for v in get_model().embed(texts)]


def embed_one(text: str) -> list[float]:
    return embed_batch([text])[0]
