"""Unit tests for vault graph: scanner, classifier, wikilinks, resolver, graph builder."""

import tempfile
from pathlib import Path

import pytest

from app.vault.wikilinks import parse_wiki_links, WikiLinkRef
from app.vault.scanner import scan_vault, parse_note_file
from app.vault.graph import classify, resolve_link, build_vault_graph, NoteKind
from app.vault.schemas import VaultGraph


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_vault(files: dict[str, str]) -> Path:
    """Create a temporary vault with the given {rel_path: content} mapping."""
    tmp = Path(tempfile.mkdtemp())
    for rel_path, content in files.items():
        fpath = tmp / rel_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    return tmp


# ── WikiLinks ──────────────────────────────────────────────────────────────────

class TestWikiLinks:
    def test_simple_link(self):
        refs = parse_wiki_links("see [[Target]] here")
        assert len(refs) == 1
        assert refs[0].target == "Target"

    def test_alias_stripped(self):
        refs = parse_wiki_links("[[Target|alias]]")
        assert len(refs) == 1
        assert refs[0].target == "Target"

    def test_heading_stripped(self):
        refs = parse_wiki_links("[[Target#Heading]]")
        assert len(refs) == 1
        assert refs[0].target == "Target"

    def test_folder_path_link(self):
        refs = parse_wiki_links("[[daily/2026-05-18]]")
        assert len(refs) == 1
        assert refs[0].target == "daily/2026-05-18"

    def test_multiple_links_deduped(self):
        refs = parse_wiki_links("[[A]] and [[B]] and [[A]] again")
        targets = [r.target for r in refs]
        assert targets == ["A", "B"]

    def test_no_links(self):
        refs = parse_wiki_links("no links here")
        assert refs == []


# ── Scanner ────────────────────────────────────────────────────────────────────

class TestScanner:
    def test_scans_markdown_files(self):
        vault = _make_vault({
            "note1.md": "---\ntitle: Note 1\n---\nContent",
            "note2.md": "Plain note without frontmatter",
        })
        notes = scan_vault(vault)
        assert len(notes) == 2

    def test_skips_excluded_dirs(self):
        vault = _make_vault({
            "note.md": "Content",
            ".obsidian/foo.md": "Should be skipped",
            "__pycache__/bar.md": "Should be skipped",
        })
        notes = scan_vault(vault)
        assert len(notes) == 1
        assert notes[0].rel_path == "note.md"

    def test_parses_frontmatter_title(self):
        vault = _make_vault({
            "note.md": "---\ntitle: My Custom Title\n---\nBody text",
        })
        notes = scan_vault(vault)
        assert notes[0].title == "My Custom Title"

    def test_falls_back_to_stem(self):
        vault = _make_vault({
            "my-note.md": "No frontmatter here",
        })
        notes = scan_vault(vault)
        assert notes[0].title == "my-note"

    def test_parses_tags(self):
        vault = _make_vault({
            "note.md": "---\ntags: [tag1, tag2]\n---\nContent",
        })
        notes = scan_vault(vault)
        assert set(notes[0].tags) == {"tag1", "tag2"}

    def test_parses_wiki_targets(self):
        vault = _make_vault({
            "note.md": "See [[Other]] for details.",
        })
        notes = scan_vault(vault)
        assert "Other" in notes[0].wiki_targets

    def test_empty_vault(self):
        vault = Path(tempfile.mkdtemp())
        notes = scan_vault(vault)
        assert notes == []

    def test_missing_vault_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_vault(Path("/nonexistent/path"))

    def test_malformed_yaml_skipped(self):
        vault = _make_vault({
            "bad.md": "---\ninvalid: yaml: [unclosed\n---\nContent",
            "good.md": "Plain content",
        })
        notes = scan_vault(vault)
        # good.md should be found; bad.md may or may not depending on parser tolerance
        assert any(n.rel_path == "good.md" for n in notes)


# ── Classifier ─────────────────────────────────────────────────────────────────

class TestClassifier:
    def _parsed(self, rel_path: str, title: str = ""):
        from app.vault.scanner import ParsedNote
        return ParsedNote(
            rel_path=rel_path,
            title=title or Path(rel_path).stem,
            tags=[],
            wiki_targets=[],
            kind="",
        )

    def test_soul(self):
        assert classify(self._parsed("SOUL.md")) == NoteKind.SOUL

    def test_user(self):
        assert classify(self._parsed("USER.md")) == NoteKind.USER

    def test_memory(self):
        assert classify(self._parsed("MEMORY.md")) == NoteKind.MEMORY

    def test_habits(self):
        assert classify(self._parsed("HABITS.md")) == NoteKind.HABITS

    def test_heartbeat(self):
        assert classify(self._parsed("HEARTBEAT.md")) == NoteKind.HEARTBEAT

    def test_daily(self):
        assert classify(self._parsed("daily/2026-05-18.md")) == NoteKind.DAILY

    def test_draft(self):
        assert classify(self._parsed("drafts/active/idea.md")) == NoteKind.DRAFT

    def test_meeting(self):
        assert classify(self._parsed("meetings/standup.md")) == NoteKind.MEETING

    def test_project(self):
        assert classify(self._parsed("projects/alpha.md")) == NoteKind.PROJECT

    def test_plain_note(self):
        assert classify(self._parsed("random.md")) == NoteKind.NOTE

    def test_nested_plain_note(self):
        assert classify(self._parsed("folder/nested.md")) == NoteKind.NOTE


# ── Link Resolver ──────────────────────────────────────────────────────────────

class TestResolver:
    def test_resolve_by_relpath(self):
        by_title = {"a": "a.md"}
        by_relpath = {"a.md": "a.md"}
        assert resolve_link("a.md", by_title, by_relpath) == "a.md"

    def test_resolve_by_title(self):
        by_title = {"b": "folder/B.md"}
        by_relpath = {"folder/B.md": "folder/B.md"}
        assert resolve_link("B", by_title, by_relpath) == "folder/B.md"

    def test_resolve_by_stem(self):
        by_title = {}
        by_relpath = {"folder/B": "folder/B.md"}
        assert resolve_link("folder/B", by_title, by_relpath) == "folder/B.md"

    def test_dangling_returns_none(self):
        assert resolve_link("DoesNotExist", {}, {}) is None


# ── Graph Builder ──────────────────────────────────────────────────────────────

class TestGraphBuilder:
    def test_empty_input(self):
        graph = build_vault_graph([])
        assert graph.nodes == []
        assert graph.edges == []

    def test_backlink_count(self):
        vault = _make_vault({
            "A.md": "Links to [[B]] and [[C]]",
            "B.md": "Links to [[C]]",
            "C.md": "No outgoing links",
        })
        notes = scan_vault(vault)
        graph = build_vault_graph(notes)

        node_map = {n.title: n for n in graph.nodes}
        assert node_map["C"].backlink_count == 2  # A→C and B→C
        assert node_map["B"].backlink_count == 1  # A→B
        assert node_map["A"].backlink_count == 0

    def test_no_self_links(self):
        vault = _make_vault({
            "A.md": "Self reference [[A]]",
        })
        notes = scan_vault(vault)
        graph = build_vault_graph(notes)
        assert len(graph.edges) == 0

    def test_dangling_links_dropped(self):
        vault = _make_vault({
            "A.md": "Links to [[DoesNotExist]]",
        })
        notes = scan_vault(vault)
        graph = build_vault_graph(notes)
        assert len(graph.edges) == 0
        assert len(graph.nodes) == 1

    def test_resolves_by_relpath_and_title(self):
        vault = _make_vault({
            "A.md": "Links to [[folder/B]] and [[B]]",
            "folder/B.md": "---\ntitle: B\n---\nContent",
        })
        notes = scan_vault(vault)
        graph = build_vault_graph(notes)
        # Both [[folder/B]] (relpath) and [[B]] (title) resolve to folder/B.md
        # Edge set deduplicates → 1 edge
        assert len(graph.edges) == 1
        assert graph.edges[0].target == "folder/B.md"

    def test_graph_vault_integration(self):
        vault = _make_vault({
            "SOUL.md": "---\ntitle: Soul\n---\nWho I am",
            "daily/2026-05-18.md": "---\ntitle: Today\n---\nReflecting on [[Soul]]",
            "random.md": "Just a note linking to [[Soul]] and [[Today]]",
        })
        notes = scan_vault(vault)
        graph = build_vault_graph(notes)

        assert len(graph.nodes) == 3
        kinds = {n.title: n.kind.value for n in graph.nodes}
        assert kinds["Soul"] == "soul"
        assert kinds["Today"] == "daily"
        assert kinds["random"] == "note"
