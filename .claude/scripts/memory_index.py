#!/home/bernd/.claude/venv/bin/python3
"""Index ~/Memory/ into the vector + keyword search database.

Usage:
  memory_index.py            # incremental: only re-index changed files
  memory_index.py --full     # drop and rebuild everything
  memory_index.py --dry-run  # show what would change, don't write

Chunking strategy:
  - Split on markdown headings (##, ###) first
  - If a section exceeds CHUNK_CHARS, split further with OVERLAP_CHARS overlap
  - Skip chunks shorter than MIN_CHUNK_CHARS (e.g. empty heading stubs)
"""
import argparse
import pathlib
import sys
import time

VAULT = pathlib.Path.home() / "Memory"
CHUNK_CHARS = 1600   # ≈ 400 tokens
OVERLAP_CHARS = 200  # ≈ 50 tokens
MIN_CHUNK_CHARS = 100

# Folders to skip (binary files, git internals, etc.)
SKIP_DIRS = {".git", ".obsidian", "__pycache__"}


def chunk_text(text: str, path: str) -> list[str]:
    """Split markdown text into overlapping chunks."""
    import re

    # Split on heading boundaries
    heading_re = re.compile(r"^#{1,3} ", re.MULTILINE)
    positions = [m.start() for m in heading_re.finditer(text)]

    if not positions:
        sections = [text]
    else:
        sections = []
        boundaries = positions + [len(text)]
        for i in range(len(positions)):
            sections.append(text[boundaries[i]: boundaries[i + 1]])

    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= CHUNK_CHARS:
            if len(section) >= MIN_CHUNK_CHARS:
                chunks.append(section)
        else:
            # Slide a window over long sections
            start = 0
            while start < len(section):
                end = start + CHUNK_CHARS
                chunk = section[start:end].strip()
                if len(chunk) >= MIN_CHUNK_CHARS:
                    chunks.append(chunk)
                if end >= len(section):
                    break
                start = end - OVERLAP_CHARS

    return chunks


def vault_files() -> list[pathlib.Path]:
    """All .md files in the vault, skipping ignored dirs."""
    files = []
    for p in VAULT.rglob("*.md"):
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        files.append(p)
    return sorted(files)


def path_key(p: pathlib.Path) -> str:
    """Stable key for a vault file (relative to home dir)."""
    return str(p.relative_to(pathlib.Path.home()))


def main():
    parser = argparse.ArgumentParser(description="Index Memory vault for RAG search")
    parser.add_argument("--full", action="store_true", help="Rebuild index from scratch")
    parser.add_argument("--dry-run", action="store_true", help="Show plan, don't write")
    args = parser.parse_args()

    # Import here so startup is fast when called from hooks
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from db import get_db
    from embeddings import embed_batch

    db = get_db()

    if args.full:
        print("Full rebuild — dropping all existing chunks")

    indexed_mtimes = {} if args.full else db.get_indexed_mtimes()
    indexed_paths = set() if args.full else db.get_all_indexed_paths()

    files = vault_files()
    file_keys = {path_key(f) for f in files}

    # Files removed from vault — clean up DB
    stale = indexed_paths - file_keys
    if stale:
        print(f"Removing {len(stale)} deleted file(s) from index")
        if not args.dry_run:
            for key in stale:
                db.delete_chunks_for_path(key)

    to_index = []
    for f in files:
        key = path_key(f)
        mtime = f.stat().st_mtime
        if key not in indexed_mtimes or indexed_mtimes[key] != mtime:
            to_index.append((f, key, mtime))

    if not to_index:
        print(f"Index up to date — {len(files)} file(s), nothing changed")
        return

    print(f"Indexing {len(to_index)} file(s) (of {len(files)} total)...")

    BATCH = 32  # embed in batches to avoid OOM on large vaults
    all_chunks_flat: list[str] = []
    chunk_meta: list[tuple[str, str, float]] = []  # (path_key, file_key, mtime)

    for f, key, mtime in to_index:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        chunks = chunk_text(text, key)
        if not chunks:
            continue
        if args.dry_run:
            print(f"  {key}: {len(chunks)} chunk(s)")
            continue
        all_chunks_flat.extend(chunks)
        for chunk in chunks:
            chunk_meta.append((chunk, key, mtime))

    if args.dry_run:
        return

    # Embed in batches
    print(f"Embedding {len(all_chunks_flat)} chunks...")
    t0 = time.time()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_chunks_flat), BATCH):
        batch = all_chunks_flat[i: i + BATCH]
        all_embeddings.extend(embed_batch(batch))
        print(f"  {min(i + BATCH, len(all_chunks_flat))}/{len(all_chunks_flat)}", end="\r")
    print(f"\nEmbedded in {time.time() - t0:.1f}s")

    # Rebuild per-file chunk lists with their embeddings
    idx = 0
    file_data: dict[str, tuple[str, float, list[str], list[list[float]]]] = {}
    for chunk_text_val, key, mtime in chunk_meta:
        if key not in file_data:
            file_data[key] = (key, mtime, [], [])
        file_data[key][2].append(chunk_text_val)
        file_data[key][3].append(all_embeddings[idx])
        idx += 1

    for key, (_, mtime, chunks, embeddings) in file_data.items():
        db.upsert_chunks(key, chunks, embeddings, mtime)

    print(f"Done — indexed {len(file_data)} file(s), {len(all_chunks_flat)} total chunks")


if __name__ == "__main__":
    main()
