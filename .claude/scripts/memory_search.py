#!/home/bernd/.claude/venv/bin/python3
"""Hybrid vector + keyword search over the indexed Memory vault.

Usage:
  memory_search.py "jira triage approach"
  memory_search.py "teams reply tone" --path-prefix Memory/drafts/sent
  memory_search.py "agent architecture" --top-k 10 --json

Hybrid merge: 0.7 × vector rank score + 0.3 × keyword rank score (RRF).
"""
import argparse
import json
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))


def rrf_merge(
    vec_results: list[dict],
    kw_results: list[dict],
    vec_weight: float = 0.7,
    kw_weight: float = 0.3,
    k: int = 5,
) -> list[dict]:
    """Reciprocal Rank Fusion with configurable weights."""
    scores: dict[str, float] = {}
    by_chunk: dict[str, dict] = {}

    for rank, r in enumerate(vec_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + vec_weight / (rank + 1)
        by_chunk[cid] = r

    for rank, r in enumerate(kw_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + kw_weight / (rank + 1)
        by_chunk[cid] = r

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
    return [
        {**by_chunk[cid], "hybrid_score": round(score, 4)}
        for cid, score in ranked
    ]


def main():
    parser = argparse.ArgumentParser(description="Search the Memory vault")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument(
        "--path-prefix",
        default=None,
        help="Filter results to paths starting with this prefix (e.g. Memory/drafts/sent)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    args = parser.parse_args()

    from db import get_db
    from embeddings import embed_one

    db = get_db()

    query_vec = embed_one(args.query)
    fetch_k = args.top_k * 4  # over-fetch to allow path filtering + merging

    vec_results = db.vector_search(query_vec, k=fetch_k, path_prefix=args.path_prefix)
    kw_results = db.keyword_search(args.query, k=fetch_k, path_prefix=args.path_prefix)
    results = rrf_merge(vec_results, kw_results, k=args.top_k)

    if not results:
        if args.json:
            print("[]")
        else:
            print("No results found.")
        return

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['path']}  (score: {r['hybrid_score']})")
        print("─" * 60)
        # Print first 300 chars of content
        snippet = r["content"][:300].strip()
        if len(r["content"]) > 300:
            snippet += "…"
        print(snippet)

    print()


if __name__ == "__main__":
    main()
