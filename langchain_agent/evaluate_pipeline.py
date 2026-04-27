#!/usr/bin/env python3
"""
Pipeline stage comparison evaluator.

Runs each stage of the retrieval pipeline (BM25 / Hybrid / Reranked) on
a query (or a list of queries) and prints offline IR metrics side-by-side.
The same metrics the Pipeline Quality Summary card uses, but in a
batch-friendly CLI.

Useful for:
  * Demo prep — find queries where stages diverge so the audience can
    actually see the pipeline earning (or not earning) its latency.
  * Regression testing — "did my reranker prompt change hurt avg NDCG?"
  * Debugging unexpected ground-truth results.

Examples:
    # Single query
    PYTHONPATH=. python evaluate_pipeline.py "tens unit muscle stimulator"

    # Multiple queries
    PYTHONPATH=. python evaluate_pipeline.py "projector" "weighted blanket"

    # Batch from a file
    PYTHONPATH=. python evaluate_pipeline.py --queries-file demo.txt

    # Auto-discover queries with high overlap against the local product
    # index (handy when ground-truth coverage is sparse)
    PYTHONPATH=. python evaluate_pipeline.py --auto-discover 20

    # Skip reranker (fast — useful when iterating on the BM25/Hybrid story)
    PYTHONPATH=. python evaluate_pipeline.py --no-rerank "projector"

    # JSON output for downstream tooling
    PYTHONPATH=. python evaluate_pipeline.py --json "sd card"
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from opensearchpy import helpers as os_helpers

from config import (
    EMBEDDINGS_MODEL,
    OPENSEARCH_INDEX_NAME,
    RERANKER_MODEL,
    RETRIEVER_FETCH_K,
    VECTOR_DIMENSION,
)
from logging_config import configure_logging
from relevancy_metrics import compute_stage_metrics
from reranker import GeminiReranker
from vector_store import OpenSearchVectorStore

logger = logging.getLogger(__name__)

# Stages we evaluate, in pipeline order
STAGES = ("bm25", "hybrid", "reranked")


# ---------------------------------------------------------------------------
# Per-query evaluation
# ---------------------------------------------------------------------------


def evaluate_query(
    vs: OpenSearchVectorStore,
    reranker: Optional[GeminiReranker],
    query: str,
    *,
    fetch_k: int,
    top_k: int,
    alpha: float,
) -> Dict[str, Any]:
    """Run all three stages on ``query`` and return per-stage metrics + latencies.

    ``reranker=None`` skips the reranker stage (its row will be omitted).
    """
    judgments = vs.lookup_judgments(query)

    # BM25 baseline
    t = time.time()
    bm25_docs = vs.bm25_only_search(query, k=fetch_k)
    bm25_ms = (time.time() - t) * 1000.0

    # Hybrid (vector + BM25)
    t = time.time()
    hybrid_docs = vs.hybrid_search(query, k=fetch_k, fetch_k=fetch_k, alpha=alpha)
    hybrid_ms = (time.time() - t) * 1000.0

    # Reranked top-k (optional)
    rerank_docs: List = []
    rerank_ms: float = 0.0
    if reranker is not None and hybrid_docs:
        t = time.time()
        scored = reranker.rerank(query, hybrid_docs, top_k)
        rerank_docs = [doc for doc, _ in scored]
        rerank_ms = (time.time() - t) * 1000.0

    bm25_ids = [d.metadata.get("product_id", "") for d in bm25_docs]
    hybrid_ids = [d.metadata.get("product_id", "") for d in hybrid_docs]
    rerank_ids = [d.metadata.get("product_id", "") for d in rerank_docs]

    if judgments:
        bm25_metrics = compute_stage_metrics(bm25_ids, judgments).to_dict()
        hybrid_metrics = compute_stage_metrics(hybrid_ids, judgments).to_dict()
        rerank_metrics = (
            compute_stage_metrics(rerank_ids, judgments).to_dict() if rerank_ids else None
        )
    else:
        bm25_metrics = hybrid_metrics = rerank_metrics = None

    stages: Dict[str, Dict[str, Any]] = {
        "bm25": {
            "latency_ms": round(bm25_ms, 1),
            "metrics": bm25_metrics,
            "top_ids": bm25_ids[:10],
        },
        "hybrid": {
            "latency_ms": round(hybrid_ms, 1),
            "metrics": hybrid_metrics,
            "top_ids": hybrid_ids[:10],
        },
    }
    if rerank_ids:
        stages["reranked"] = {
            "latency_ms": round(rerank_ms, 1),
            "metrics": rerank_metrics,
            "top_ids": rerank_ids[:10],
        }

    return {
        "query": query,
        "has_ground_truth": judgments is not None,
        "judgments_in_index": len(judgments) if judgments else 0,
        "alpha": alpha,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Auto-discover candidate queries from the judgments index
# ---------------------------------------------------------------------------


def auto_discover(
    vs: OpenSearchVectorStore,
    *,
    top_n: int,
    min_overlap: int = 3,
) -> List[str]:
    """Return up to ``top_n`` queries with the most relevant local-product overlap.

    "Relevant" = ESCI label E (Exact) or S (Substitute). The overlap is computed
    against the products in the local ``OPENSEARCH_INDEX_NAME`` index, so the
    returned queries are the ones likeliest to give meaningful per-stage NDCG.
    """
    logger.info("Loading local product_ids for overlap calculation...")
    product_ids = set()
    for hit in os_helpers.scan(
        vs.client,
        index=OPENSEARCH_INDEX_NAME,
        query={"_source": ["product_id"], "query": {"term": {"collection_id": "esci_products"}}},
        size=2000,
    ):
        pid = hit["_source"].get("product_id")
        if pid:
            product_ids.add(pid)
    logger.info("Local product index has %d unique product_ids", len(product_ids))

    logger.info("Scanning esci_judgments for overlap...")
    candidates: List[Tuple[int, str]] = []
    for hit in os_helpers.scan(vs.client, index="esci_judgments", size=2000):
        src = hit["_source"]
        relevant_local = sum(
            1
            for j in src.get("judgments", [])
            if j["esci_label"] in {"E", "S"} and j["product_id"] in product_ids
        )
        if relevant_local >= min_overlap:
            candidates.append((relevant_local, src["query"]))

    candidates.sort(reverse=True)
    return [q for _, q in candidates[:top_n]]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_metric(m: Optional[Dict[str, float]], key: str, width: int = 8) -> str:
    if m is None:
        return f"{'—':>{width}}"
    return f"{m[key]:>{width}.3f}"


def print_table(results: List[Dict[str, Any]]) -> None:
    """Render the per-query / per-stage comparison as a fixed-width table."""
    header = (
        f"{'Query':<40} {'Stage':<10} {'NDCG@10':>8} {'MRR':>6} {'R@20':>6} "
        f"{'P@10':>6} {'judged':>7} {'Latency':>9}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        gt_marker = "" if r["has_ground_truth"] else "  (no ground truth)"
        for stage_name in STAGES:
            stage = r["stages"].get(stage_name)
            if stage is None:
                continue
            m = stage["metrics"]
            judged = f"{m['judged_count']}/10" if m else "—"
            print(
                f"{(r['query'][:40] if stage_name == 'bm25' else ''):<40} "
                f"{stage_name:<10} "
                f"{format_metric(m, 'ndcg10')} "
                f"{format_metric(m, 'mrr', 6)} "
                f"{format_metric(m, 'recall20', 6)} "
                f"{format_metric(m, 'precision10', 6)} "
                f"{judged:>7} "
                f"{stage['latency_ms']:>7.0f}ms"
            )

        # Ground-truth lift summary line — what the audience cares about.
        if r["has_ground_truth"]:
            stages = r["stages"]
            bm25_n = stages["bm25"]["metrics"]["ndcg10"]
            hybrid_n = stages["hybrid"]["metrics"]["ndcg10"]
            rerank_n = stages.get("reranked", {}).get("metrics", {})
            rerank_n = rerank_n["ndcg10"] if rerank_n else None
            hybrid_lift = hybrid_n - bm25_n
            rerank_lift = (rerank_n - hybrid_n) if rerank_n is not None else None
            summary = f"  Hybrid Δ={_fmt_delta(hybrid_lift)}"
            if rerank_lift is not None:
                summary += f"   Rerank Δ={_fmt_delta(rerank_lift)}"
            print(f"{'':<40} {summary}{gt_marker}")
        else:
            print(f"{'':<40}  {gt_marker}")
        print()


def _fmt_delta(d: float) -> str:
    if abs(d) < 0.005:
        return "±0.000"
    return f"{d:+.3f}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("query", nargs="*", help="Query string(s) to evaluate")
    parser.add_argument("--queries-file", type=Path, help="File with one query per line")
    parser.add_argument(
        "--auto-discover",
        type=int,
        metavar="N",
        help="Pick the N queries with the most relevant-product overlap in the local index",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.25,
        help="Hybrid alpha (0=pure lexical, 1=pure vector). Default: 0.25",
    )
    parser.add_argument(
        "--fetch-k",
        type=int,
        default=RETRIEVER_FETCH_K,
        help=f"Candidates to fetch per stage (default: {RETRIEVER_FETCH_K})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Final top-k for the reranker stage (default: 10, matches NDCG@10 cutoff)",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip the reranker stage (much faster — useful when iterating on BM25/Hybrid)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for the full result set instead of a human-readable table",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    configure_logging()
    args = parse_args(argv)

    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDINGS_MODEL, output_dimensionality=VECTOR_DIMENSION
    )
    vs = OpenSearchVectorStore(embeddings, collection_id="esci_products")

    queries: List[str] = list(args.query)
    if args.queries_file:
        queries.extend(
            line.strip()
            for line in args.queries_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    if args.auto_discover:
        discovered = auto_discover(vs, top_n=args.auto_discover)
        logger.info("Auto-discovered %d queries with overlap", len(discovered))
        queries.extend(discovered)
    if not queries:
        print("No queries provided. Pass query strings, --queries-file, or --auto-discover N.")
        return 2

    reranker: Optional[GeminiReranker] = None
    if not args.no_rerank:
        reranker = GeminiReranker(model_name=RERANKER_MODEL)

    results: List[Dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        if not args.json:
            print(f"[{i}/{len(queries)}] evaluating: {q!r}")
        results.append(
            evaluate_query(
                vs,
                reranker,
                q,
                fetch_k=args.fetch_k,
                top_k=args.top_k,
                alpha=args.alpha,
            )
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print()
        print_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
