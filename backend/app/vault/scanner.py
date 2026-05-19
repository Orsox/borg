import frontmatter
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
import logging
import yaml
from .wikilinks import parse_wiki_links

# Setup logging (matching standard internal pattern)
logger = logging.getLogger(__name__)

# Define excluded directories/suffixes to prevent scanning junk data
EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".obsidian", ".trash", "expired"}


@dataclass(frozen=True)
class ParsedNote:
    """A dataclass holding the structured, pre-processed data for a single markdown file."""
    rel_path: str          # Path relative to vault root (e.g., 'daily/2026-05-18')
    title: str             # Canonical title of the note
    tags: List[str]        # List of extracted tags
    wiki_targets: List[str] # List of resolved wiki targets from links
    kind: str              # Classification (e.g., 'daily', 'soul', 'note')

def parse_note_file(file_path: Path, vault_root: Path) -> ParsedNote | None:
    """
    Reads a markdown file using python-frontmatter, extracts metadata, 
    and returns a ParsedNote object. Handles exceptions gracefully.
    """
    try:
        # Use frontmatter.load to safely parse YAML/Markdown boundaries
        post = frontmatter.load(file_path)
        content = post.content
        metadata = post.metadata

        # 1. Title extraction (Obsidian convention: title or filename stem)
        title = metadata.get("title") or file_path.stem

        # 2. Tags extraction
        raw_tags = metadata.get("tags", [])
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        elif isinstance(raw_tags, list):
             # Already a list or mixed format (handle both)
            tags = []
            for item in raw_tags:
                if isinstance(item, str):
                    tags.extend([t.strip() for t in item.split(',') if t.strip()])

        # 3. Wiki Links extraction
        wiki_targets = parse_wiki_links(content)

        parsed_note = ParsedNote(
            rel_path=str(file_path.relative_to(vault_root)),
            title=title,
            tags=list(set([t for t in tags if t])), # Ensure unique and non-empty tags
            wiki_targets=[link.target for link in wiki_targets],
            kind="" # Placeholder; kind is set by graph builder later
        )
        return parsed_note

    except yaml.YAMLError as e:
        logger.warning(f"YAML error parsing {file_path}: {e}. Skipping file.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing {file_path}: {type(e).__name__} - {e}")
        return None

def scan_vault(vault_path: Path) -> List[ParsedNote]:
    """
    Recursively scans the entire vault directory for markdown files, 
    parsing metadata and links from each.
    Returns a list of ParsedNote objects.
    """
    if not vault_path.exists() or not vault_path.is_dir():
        raise FileNotFoundError(f"Vault path does not exist or is not a directory: {vault_path}")

    assets = []
    logger.info(f"Starting scan of vault at {vault_path}...")
    
    # rglob recursively finds all files matching *.md extension
    for file_path in vault_path.rglob("*.md"):
        parts = list(file_path.parts)
        
        # Skip any directory/file path part that matches an excluded pattern
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        
        parsed = parse_note_file(file_path, vault_root=vault_path)
        if parsed is not None:
            assets.append(parsed)

    logger.info(f"Scan complete. Found {len(assets)} valid notes.")
    return assets