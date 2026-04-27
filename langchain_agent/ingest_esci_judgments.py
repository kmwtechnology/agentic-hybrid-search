#!/usr/bin/env python3
"""
ESCI Judgments Ingestion Script.

Loads the Amazon Shopping Queries Dataset judgments
(``shopping_queries_dataset_examples.parquet``) and indexes one document
*per query* into a dedicated ``esci_judgments`` OpenSearch index.

Each indexed document contains a nested array of judged products with the
ESCI label (E/S/C/I) and a numeric relevance score on the standard ESCI
scale used by the dataset paper:

    E (Exact)        -> 4.0
    S (Substitute)   -> 1.0
    C (Complement)   -> 0.1
    I (Irrelevant)   -> 0.0

These judgments power the Pipeline Quality Summary card by giving us
ground-truth NDCG/MRR/Recall@k/Precision@k for queries that match the
dataset corpus.

Usage:
    PYTHONPATH=. python ingest_esci_judgments.py            # ingest US judgments
    PYTHONPATH=. python ingest_esci_judgments.py --limit 1000   # cap to N queries
    PYTHONPATH=. python ingest_esci_judgments.py --reset    # drop + recreate index
    PYTHONPATH=. python ingest_esci_judgments.py --append   # add to existing index
    PYTHONPATH=. python ingest_esci_judgments.py --stats    # show index stats only
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
from opensearchpy import OpenSearch
from opensearchpy import helpers as os_helpers

from logging_config import configure_logging
from vector_store import create_opensearch_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JUDGMENTS_INDEX_NAME = "esci_judgments"

# ESCI relevance scale (Reddy et al., 2022 — Section 4)
ESCI_RELEVANCE: Dict[str, float] = {
    "E": 4.0,  # Exact
    "S": 1.0,  # Substitute
    "C": 0.1,  # Complement
    "I": 0.0,  # Irrelevant
}

BASE_DIR = Path(__file__).parent
JUDGMENTS_PARQUET = (
    BASE_DIR.parent
    / "esci"
    / "shopping_queries_dataset"
    / "shopping_queries_dataset_examples.parquet"
)

DEFAULT_LOCALE = "us"
BULK_BATCH_SIZE = 1000

JUDGMENTS_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "30s",
        },
    },
    "mappings": {
        "properties": {
            "query_id": {"type": "keyword"},
            "query": {
                "type": "text",
                "fields": {
                    "keyword": {"type": "keyword", "normalizer": "lowercase"},
                },
            },
            "locale": {"type": "keyword"},
            "split": {"type": "keyword"},
            "small_version": {"type": "boolean"},
            "large_version": {"type": "boolean"},
            "num_judgments": {"type": "integer"},
            "label_counts": {
                "properties": {
                    "E": {"type": "integer"},
                    "S": {"type": "integer"},
                    "C": {"type": "integer"},
                    "I": {"type": "integer"},
                }
            },
            "judgments": {
                "type": "nested",
                "properties": {
                    "product_id": {"type": "keyword"},
                    "esci_label": {"type": "keyword"},
                    "relevance": {"type": "float"},
                },
            },
        }
    },
}

# OpenSearch ships ``lowercase`` as a built-in normalizer in 2.x but newer
# images sometimes require an explicit declaration. Add it defensively.
JUDGMENTS_MAPPING["settings"]["analysis"] = {
    "normalizer": {
        "lowercase": {
            "type": "custom",
            "char_filter": [],
            "filter": ["lowercase"],
        }
    }
}


# ---------------------------------------------------------------------------
# Loading + aggregation
# ---------------------------------------------------------------------------


def load_judgments(parquet_path: Path, locale: str) -> pd.DataFrame:
    """Read the ESCI examples parquet and filter to the requested locale."""
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"ESCI judgments parquet not found at {parquet_path}. "
            "Download the Shopping Queries Dataset to esci/shopping_queries_dataset/."
        )

    logger.info("Loading judgments parquet", extra={"path": str(parquet_path)})
    df = pd.read_parquet(parquet_path)
    logger.info(
        "Loaded judgments",
        extra={"rows": len(df), "columns": list(df.columns)},
    )
    if locale:
        df = df[df["product_locale"] == locale].copy()
        logger.info("Filtered to locale", extra={"locale": locale, "rows": len(df)})
    return df


def aggregate_per_query(df: pd.DataFrame) -> Iterable[Dict]:
    """Group judgments per query and yield one document per query_id."""
    # Sort by relevance desc so the nested array is naturally pre-sorted, which
    # makes manual inspection (and tie-breaking) deterministic.
    df = df.assign(relevance=df["esci_label"].map(ESCI_RELEVANCE).astype(float))
    df = df.sort_values(["query_id", "relevance"], ascending=[True, False])

    for query_id, group in df.groupby("query_id", sort=False):
        first = group.iloc[0]
        label_counts = group["esci_label"].value_counts().to_dict()
        judgments = [
            {
                "product_id": str(row.product_id),
                "esci_label": str(row.esci_label),
                "relevance": float(row.relevance),
            }
            for row in group.itertuples(index=False)
        ]
        yield {
            "query_id": str(query_id),
            "query": str(first.query).strip(),
            "locale": str(first.product_locale),
            "split": str(first.split),
            "small_version": bool(int(first.small_version)),
            "large_version": bool(int(first.large_version)),
            "num_judgments": len(judgments),
            "label_counts": {label: int(label_counts.get(label, 0)) for label in "ESCI"},
            "judgments": judgments,
        }


# ---------------------------------------------------------------------------
# OpenSearch operations
# ---------------------------------------------------------------------------


def ensure_index(client: OpenSearch, *, reset: bool) -> None:
    """Create the judgments index if missing; recreate when ``reset=True``."""
    exists = client.indices.exists(index=JUDGMENTS_INDEX_NAME)
    if exists and reset:
        logger.warning("Deleting existing index", extra={"index": JUDGMENTS_INDEX_NAME})
        client.indices.delete(index=JUDGMENTS_INDEX_NAME)
        exists = False
    if not exists:
        logger.info("Creating index", extra={"index": JUDGMENTS_INDEX_NAME})
        client.indices.create(index=JUDGMENTS_INDEX_NAME, body=JUDGMENTS_MAPPING)


def index_judgments(
    client: OpenSearch,
    docs: Iterable[Dict],
    *,
    limit: Optional[int] = None,
) -> int:
    """Bulk-index aggregated judgment docs into OpenSearch.

    Returns the number of documents indexed.
    """

    def actions() -> Iterable[Dict]:
        count = 0
        for doc in docs:
            if limit is not None and count >= limit:
                break
            yield {
                "_op_type": "index",
                "_index": JUDGMENTS_INDEX_NAME,
                "_id": doc["query_id"],
                "_source": doc,
            }
            count += 1

    indexed = 0
    started = time.time()
    for ok, item in os_helpers.streaming_bulk(
        client,
        actions(),
        chunk_size=BULK_BATCH_SIZE,
        request_timeout=120,
        raise_on_error=False,
        max_retries=3,
        initial_backoff=2,
    ):
        if not ok:
            logger.error("Bulk index error", extra={"item": item})
            continue
        indexed += 1
        if indexed % 5000 == 0:
            elapsed = time.time() - started
            rate = indexed / elapsed if elapsed > 0 else 0.0
            logger.info(
                "Bulk progress",
                extra={
                    "indexed": indexed,
                    "elapsed_s": round(elapsed, 1),
                    "docs_per_s": round(rate, 1),
                },
            )
    client.indices.refresh(index=JUDGMENTS_INDEX_NAME)
    return indexed


def show_stats(client: OpenSearch) -> None:
    """Print summary stats for the judgments index."""
    if not client.indices.exists(index=JUDGMENTS_INDEX_NAME):
        print(f"Index '{JUDGMENTS_INDEX_NAME}' does not exist.")
        return
    count = client.count(index=JUDGMENTS_INDEX_NAME)["count"]
    sample = client.search(
        index=JUDGMENTS_INDEX_NAME,
        body={
            "size": 0,
            "aggs": {
                "by_locale": {"terms": {"field": "locale", "size": 10}},
                "by_split": {"terms": {"field": "split", "size": 10}},
                "judgments_per_query": {"stats": {"field": "num_judgments"}},
            },
        },
    )
    print(f"Index: {JUDGMENTS_INDEX_NAME}")
    print(f"  Documents: {count:,}")
    print(f"  Locales: {sample['aggregations']['by_locale']['buckets']}")
    print(f"  Splits: {sample['aggregations']['by_split']['buckets']}")
    stats = sample["aggregations"]["judgments_per_query"]
    print(
        "  Judgments per query: "
        f"min={stats['min']:.0f} max={stats['max']:.0f} avg={stats['avg']:.1f} "
        f"total={stats['sum']:.0f}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--locale", default=DEFAULT_LOCALE, help="Filter to this product locale (default: us)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of queries indexed (useful for smoke tests)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate the judgments index before indexing (default behavior when index missing)",
    )
    group.add_argument(
        "--append",
        action="store_true",
        help="Append to existing index without recreating (use after schema-compatible additions)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print index stats and exit",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    configure_logging()
    args = parse_args(argv)

    client = create_opensearch_client()

    if args.stats:
        show_stats(client)
        return 0

    # Default behavior: recreate when not explicitly --append
    reset = args.reset or not args.append

    df = load_judgments(JUDGMENTS_PARQUET, args.locale)
    if df.empty:
        logger.error("No judgments to index after locale filter", extra={"locale": args.locale})
        return 2

    ensure_index(client, reset=reset)
    indexed = index_judgments(client, aggregate_per_query(df), limit=args.limit)
    logger.info("Ingestion complete", extra={"queries_indexed": indexed})
    show_stats(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
