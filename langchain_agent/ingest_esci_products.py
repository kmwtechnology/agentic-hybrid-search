#!/usr/bin/env python3
"""
Amazon ESCI E-Commerce Product Ingestion Script

Ingests product data from the Amazon Shopping Queries Dataset (ESCI)
into OpenSearch for hybrid search over e-commerce product listings.

Uses cached parquet samples for idempotent ingestion:
- esci_products_sample_10000.parquet — default 10K English (US) products
- esci_products_sample_{limit}.parquet — custom sample sizes

Usage:
    python ingest_esci_products.py              # Ingest default 10K sample
    python ingest_esci_products.py --limit N    # Custom sample size
    python ingest_esci_products.py --resample   # Force re-sample
    python ingest_esci_products.py --all        # Ingest all EN products
    python ingest_esci_products.py --stats      # Show index stats only
    python ingest_esci_products.py --reset-index # Delete and recreate index (for mapping changes)
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd
from opensearchpy import helpers as os_helpers
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import (
    EMBEDDINGS_MODEL,
    VECTOR_DIMENSION,
    OPENSEARCH_INDEX_NAME,
    CHUNKING_STRATEGY,
)
from vector_store import create_opensearch_client, INDEX_MAPPING, SEARCH_PIPELINE, OPENSEARCH_SEARCH_PIPELINE

logger = logging.getLogger(__name__)

# Chunking settings — only used if CHUNKING_STRATEGY enables chunking for the collection
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# ESCI product collection
ESCI_COLLECTION_NAME = "esci_products"

# Path to ESCI dataset
BASE_DIR = Path(__file__).parent
ESCI_DATASET_DIR = BASE_DIR.parent / "esci" / "shopping_queries_dataset"
ESCI_PRODUCTS_FILE = ESCI_DATASET_DIR / "shopping_queries_dataset_products.parquet"

# Default ingestion parameters
DEFAULT_LIMIT = 10000
PRODUCT_LOCALE = "us"
EMBEDDING_BATCH_SIZE = 250  # Products per embedding API call (optimized for throughput vs latency)
SAVE_INTERVAL = 20  # Flush embeddings to parquet every N batches (~5K products at 250/batch = 5K products per save)
FULL_US_PARQUET = ESCI_DATASET_DIR / "esci_products_full_us.parquet"  # canonical full-set cache


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        start = end - overlap
        if end == len(text):
            break

    return chunks


def load_or_create_sample(limit: int = DEFAULT_LIMIT, force_resample: bool = False) -> pd.DataFrame:
    """
    Load or create a cached sample of products.

    Returns DataFrame with products (embeddings may be None if not yet generated).

    Args:
        limit: Number of products to sample (default 10000)
        force_resample: If True, ignore cached sample and resample

    Returns:
        DataFrame with sampled products (may include cached 'embedding' column)

    Raises:
        FileNotFoundError: If neither cached sample nor full products file exists
    """
    sample_file = ESCI_DATASET_DIR / f"esci_products_sample_{limit}.parquet"

    # Return cached sample if it exists and not forcing resample
    if sample_file.exists() and not force_resample:
        logger.info(f"Loading cached sample from {sample_file.name}")
        df_sample = pd.read_parquet(sample_file)
        has_embeddings = "embedding" in df_sample.columns
        logger.info(f"  Products: {len(df_sample)}, Embeddings cached: {has_embeddings}")
        return df_sample

    # If no cached sample and force_resample, need the full products file
    if not ESCI_PRODUCTS_FILE.exists():
        raise FileNotFoundError(f"ESCI products file not found: {ESCI_PRODUCTS_FILE}\n"
                                f"Cached sample not available either: {sample_file}")

    # Load full dataset and filter to US English products
    logger.info(f"Loading products from {ESCI_PRODUCTS_FILE.name}...")
    df = pd.read_parquet(ESCI_PRODUCTS_FILE)

    logger.info(f"Total products: {len(df)}")

    # Filter to US English products only
    df_us = df[df["product_locale"] == PRODUCT_LOCALE].copy()
    logger.info(f"US products: {len(df_us)}")

    # Deduplicate by product_id (keep first occurrence)
    df_us_dedup = df_us.drop_duplicates(subset=["product_id"], keep="first").copy()
    duplicates_removed = len(df_us) - len(df_us_dedup)
    if duplicates_removed > 0:
        logger.info(f"Deduplicated: removed {duplicates_removed} duplicate product_ids")
        print(f"   Deduplicated: removed {duplicates_removed:,} duplicate product_ids", flush=True)
    logger.info(f"Unique US products: {len(df_us_dedup)}")

    # Sample deterministically
    if limit < len(df_us_dedup):
        df_sample = df_us_dedup.sample(n=limit, random_state=42)
        logger.info(f"Sampled {limit} US products (deterministic, seed=42)")
    else:
        df_sample = df_us_dedup
        logger.info(f"Using all {len(df_us_dedup)} unique US products (limit {limit} >= dataset size)")

    # Initialize embedding column as None (will be populated during ingestion)
    df_sample["embedding"] = None

    # Cache the sample parquet for idempotent future runs
    ESCI_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df_sample.to_parquet(sample_file)
    logger.info(f"Cached sample to {sample_file.name}")

    return df_sample


def ensure_index_exists(client, reset_index: bool = False):
    """Create the OpenSearch index if it doesn't exist. Optionally delete existing first."""
    try:
        index_exists_before = client.indices.exists(index=OPENSEARCH_INDEX_NAME)
        logger.info(f"[ensure_index_exists] reset_index={reset_index}, index_exists_before={index_exists_before}")
        print(f"   [Index state] exists={index_exists_before}, reset_index={reset_index}", flush=True)

        if reset_index and index_exists_before:
            logger.info(f"[ensure_index_exists] Attempting to delete index '{OPENSEARCH_INDEX_NAME}'...")
            print(f"   Deleting existing index '{OPENSEARCH_INDEX_NAME}'...", flush=True)
            client.indices.delete(index=OPENSEARCH_INDEX_NAME)
            logger.info(f"[ensure_index_exists] ✓ Successfully deleted index '{OPENSEARCH_INDEX_NAME}'")
            print(f"   ✓ Deleted existing index '{OPENSEARCH_INDEX_NAME}'", flush=True)

            # Verify deletion
            index_exists_after_delete = client.indices.exists(index=OPENSEARCH_INDEX_NAME)
            logger.info(f"[ensure_index_exists] Verification: index_exists_after_delete={index_exists_after_delete}")
            print(f"   [Verification] Index exists after delete: {index_exists_after_delete}", flush=True)
        else:
            if reset_index:
                logger.info(f"[ensure_index_exists] reset_index=true but index doesn't exist (already deleted?)")
                print(f"   [Note] reset_index=true but index doesn't exist", flush=True)

        # Now create if needed
        index_exists_now = client.indices.exists(index=OPENSEARCH_INDEX_NAME)
        if not index_exists_now:
            logger.info(f"[ensure_index_exists] Creating new index '{OPENSEARCH_INDEX_NAME}'...")
            print(f"   Creating new index '{OPENSEARCH_INDEX_NAME}'...", flush=True)
            client.indices.create(index=OPENSEARCH_INDEX_NAME, body=INDEX_MAPPING)
            logger.info(f"[ensure_index_exists] ✓ Created index '{OPENSEARCH_INDEX_NAME}'")
            print(f"   ✓ Created index '{OPENSEARCH_INDEX_NAME}'", flush=True)
        else:
            logger.info(f"[ensure_index_exists] Index '{OPENSEARCH_INDEX_NAME}' already exists (not recreated)")
            print(f"   [Note] Index '{OPENSEARCH_INDEX_NAME}' already exists", flush=True)

        # Create search pipeline
        try:
            client.transport.perform_request(
                "PUT",
                f"/_search/pipeline/{OPENSEARCH_SEARCH_PIPELINE}",
                body=SEARCH_PIPELINE,
            )
            logger.info(f"Search pipeline '{OPENSEARCH_SEARCH_PIPELINE}' created/updated")
        except Exception as e:
            logger.warning(f"Could not create search pipeline: {e}")

    except Exception as e:
        logger.error(f"Error ensuring index exists: {e}")
        raise



def get_indexed_product_ids(client) -> set:
    """Get set of product IDs already indexed in OpenSearch using composite aggregation pagination."""
    product_ids = set()
    after_key = None
    try:
        while True:
            body = {
                "size": 0,
                "aggs": {
                    "product_ids": {
                        "composite": {
                            "size": 1000,
                            "sources": [{"product_id": {"terms": {"field": "product_id"}}}],
                        }
                    }
                }
            }
            if after_key:
                body["aggs"]["product_ids"]["composite"]["after"] = after_key

            response = client.search(index=OPENSEARCH_INDEX_NAME, body=body)
            buckets = response["aggregations"]["product_ids"]["buckets"]
            for bucket in buckets:
                product_ids.add(bucket["key"]["product_id"])

            after_key = response["aggregations"]["product_ids"].get("after_key")
            if not after_key or len(buckets) < 1000:
                break

        logger.info(f"Found {len(product_ids):,} products already indexed")
        print(f"   Found {len(product_ids):,} products already indexed in OpenSearch", flush=True)
        return product_ids
    except Exception as e:
        logger.warning(f"Could not fetch indexed product IDs: {e}")
        return product_ids


def _prepare_product(row, df_idx) -> Optional[Dict]:
    """Prepare a product row for ingestion. Returns dict with fields or None if skipped."""
    product_id = str(row.get("product_id", ""))
    title = str(row.get("product_title", ""))
    description = str(row.get("product_description", ""))
    bullet_points = str(row.get("product_bullet_point", ""))
    brand = str(row.get("product_brand", ""))
    color = str(row.get("product_color", ""))
    locale = str(row.get("product_locale", "us"))

    text = "\n".join([t for t in [title, description, bullet_points] if t and str(t).strip()])
    if not text or len(text) < 50:
        return None

    # Parse cached embedding
    cached_embedding = row.get("embedding")
    if cached_embedding is not None and isinstance(cached_embedding, str):
        try:
            cached_embedding = json.loads(cached_embedding)
        except (json.JSONDecodeError, ValueError):
            cached_embedding = None
    if cached_embedding is not None and not isinstance(cached_embedding, list):
        cached_embedding = None

    return {
        "df_idx": df_idx,
        "product_id": product_id,
        "title": title,
        "brand": brand,
        "color": color,
        "locale": locale,
        "text": text,
        "cached_embedding": cached_embedding,
    }


def _ingest_batch(
    batch: List[Dict],
    embeddings: GoogleGenerativeAIEmbeddings,
    client,
) -> Tuple[int, int, List[Tuple]]:
    """
    Embed and index a batch of products.

    Uses embed_documents() for all products needing new embeddings (single API call per batch).

    Returns:
        Tuple of (docs_inserted, chunks_inserted, [(df_idx, embedding)] for parquet update)
    """
    strategy = CHUNKING_STRATEGY.get(ESCI_COLLECTION_NAME, {})
    use_chunking = strategy.get("enabled", False)

    # Separate products with/without cached embeddings
    need_embedding = []
    have_embedding = []
    for item in batch:
        if item["cached_embedding"] is not None:
            have_embedding.append(item)
        else:
            need_embedding.append(item)

    # Batch embed all products needing new embeddings (single API call, no retry here — caller handles rate limits)
    new_embeddings = []
    if need_embedding:
        texts = [item["text"] for item in need_embedding]
        new_embeddings = embeddings.embed_documents(texts)

    # Build OpenSearch bulk actions
    actions = []
    parquet_updates = []

    for item in have_embedding:
        chunks = chunk_text(item["text"]) if use_chunking else [item["text"]]
        for chunk_idx, chunk in enumerate(chunks):
            actions.append({
                "_index": OPENSEARCH_INDEX_NAME,
                "_id": f"{item['product_id']}-{chunk_idx}",
                "_source": {
                    "document_id": item["product_id"],
                    "collection_id": ESCI_COLLECTION_NAME,
                    "source": "esci/shopping_queries_dataset",
                    "title": item["title"],
                    "doc_type": "product",
                    "product_id": item["product_id"],
                    "product_brand": item["brand"],
                    "product_color": item["color"],
                    "product_locale": item["locale"],
                    "chunk_index": chunk_idx,
                    "chunk_text": chunk,
                    "embedding": item["cached_embedding"],
                    "title_suggest": item["title"],
                    "brand_suggest": item["brand"],
                    "title_phrase": item["title"],
                    "title_phonetic": item["title"],
                    "brand_phonetic": item["brand"],
                },
            })

    for i, item in enumerate(need_embedding):
        emb = new_embeddings[i]
        parquet_updates.append((item["df_idx"], emb))
        chunks = chunk_text(item["text"]) if use_chunking else [item["text"]]
        for chunk_idx, chunk in enumerate(chunks):
            actions.append({
                "_index": OPENSEARCH_INDEX_NAME,
                "_id": f"{item['product_id']}-{chunk_idx}",
                "_source": {
                    "document_id": item["product_id"],
                    "collection_id": ESCI_COLLECTION_NAME,
                    "source": "esci/shopping_queries_dataset",
                    "title": item["title"],
                    "doc_type": "product",
                    "product_id": item["product_id"],
                    "product_brand": item["brand"],
                    "product_color": item["color"],
                    "product_locale": item["locale"],
                    "chunk_index": chunk_idx,
                    "chunk_text": chunk,
                    "embedding": emb,
                    "title_suggest": item["title"],
                    "brand_suggest": item["brand"],
                    "title_phrase": item["title"],
                    "title_phonetic": item["title"],
                    "brand_phonetic": item["brand"],
                },
            })

    docs_inserted = 0
    chunks_inserted = 0
    if actions and client:
        success, errors = os_helpers.bulk(client, actions, refresh=False)
        if errors:
            logger.warning(f"Bulk ingestion errors: {errors}")
        docs_inserted = len(batch)
        chunks_inserted = len(actions)

    return docs_inserted, chunks_inserted, parquet_updates


def _flush_embeddings_to_parquet(df: pd.DataFrame, embedding_cache: dict, sample_file: Path) -> None:
    """Write pending embeddings from embedding_cache into df and save to parquet."""
    if not embedding_cache:
        return
    if "embedding" not in df.columns:
        df["embedding"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    for df_idx, emb in embedding_cache.items():
        df.at[df_idx, "embedding"] = emb
    try:
        df.to_parquet(sample_file)
        print(f"   [checkpoint] Saved {len(embedding_cache):,} embeddings → {sample_file.name}", flush=True)
    except Exception as e:
        logger.warning(f"Could not save embeddings to parquet: {e}")


def ingest_esci_products(
    limit: int = DEFAULT_LIMIT,
    force_resample: bool = False,
    all_products: bool = False,
    reset_index: bool = False,
) -> Tuple[int, int]:
    """
    Ingest ESCI products into OpenSearch with batched embedding and verbose progress.

    Embeddings are generated in batches via embed_documents() (one API call per batch).
    Embeddings are cached in the sample parquet file to avoid regeneration.
    Products already indexed in OpenSearch are skipped (unless reset_index=True).

    Args:
        limit: Number of products to sample (ignored if all_products=True)
        force_resample: If True, force re-sampling even if cached
        all_products: If True, ingest all US products (no sampling)
        reset_index: If True, delete existing index before creating new one

    Returns:
        Tuple of (total_products_ingested, total_chunks_created)
    """
    print("\n📦 Ingesting ESCI E-Commerce Products...")

    # Load or create sample
    if all_products:
        print(f"   Loading all unique US English products...")
        if FULL_US_PARQUET.exists() and not force_resample:
            print(f"   Loading cached full US dataset from {FULL_US_PARQUET.name}...", flush=True)
            df = pd.read_parquet(FULL_US_PARQUET)
        else:
            # Load all unique US products from source parquet (no arbitrary limit)
            df = load_or_create_sample(limit=10000000, force_resample=True)  # use very high limit to get all
        sample_file = FULL_US_PARQUET  # all saves (incremental + final) go here
    else:
        print(f"   Loading {limit} product sample...")
        df = load_or_create_sample(limit=limit, force_resample=force_resample)
        sample_file = ESCI_DATASET_DIR / f"esci_products_sample_{limit}.parquet"

    if df.empty:
        print("   ⚠️  No products loaded")
        return 0, 0

    # Initialize OpenSearch client
    client = create_opensearch_client()
    logger.info(f"[ingest_esci_products] Initializing index with reset_index={reset_index}")
    ensure_index_exists(client, reset_index=reset_index)

    # Check which products are already indexed
    logger.info(f"[ingest_esci_products] Checking indexed product IDs...")
    indexed_ids = get_indexed_product_ids(client)
    logger.info(f"[ingest_esci_products] Found {len(indexed_ids)} products already indexed")
    print(f"   Found {len(indexed_ids)} products already in index", flush=True)

    products_to_ingest = [idx for idx, row in df.iterrows()
                          if str(row.get("product_id", "")) not in indexed_ids]

    logger.info(f"[ingest_esci_products] Products to ingest: {len(products_to_ingest)}/{len(df)}")
    print(f"   Products to ingest: {len(products_to_ingest)}/{len(df)}", flush=True)

    if not products_to_ingest:
        logger.warning(f"[ingest_esci_products] All {len(df)} products already indexed - skipping ingestion")
        print(f"   ✓ All {len(df)} products already indexed in OpenSearch")
        return 0, 0

    total_new = len(products_to_ingest)
    print(f"   Processing {total_new}/{len(df)} new products (batch size: {EMBEDDING_BATCH_SIZE})...", flush=True)

    # Initialize embeddings
    embeddings_model = GoogleGenerativeAIEmbeddings(
        model=EMBEDDINGS_MODEL,
        output_dimensionality=VECTOR_DIMENSION,
    )

    # Prepare all product data
    print(f"   Preparing product texts...")
    prepared = []
    skipped = 0
    for idx in products_to_ingest:
        row = df.loc[idx]
        item = _prepare_product(row, idx)
        if item:
            prepared.append(item)
        else:
            skipped += 1

    cached_count = sum(1 for p in prepared if p["cached_embedding"] is not None)
    need_embed_count = len(prepared) - cached_count
    print(f"   Prepared {len(prepared)} products ({cached_count} cached embeddings, {need_embed_count} need embedding, {skipped} skipped)", flush=True)

    # Ensure embedding column exists (may be missing if parquet was created without it)
    if "embedding" not in df.columns:
        df["embedding"] = None

    # Process in batches
    total_docs = 0
    total_chunks = 0
    embeddings_updated = False
    embedding_cache = {}  # df_idx -> embedding list (written to parquet at end)
    start_time = time.time()
    num_batches = (len(prepared) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
    batch_delay = 0.0  # seconds to wait between batches (adjusted on rate limit)

    for batch_num in range(num_batches):
        # Pace requests to stay within rate limit
        if batch_delay > 0 and batch_num > 0:
            time.sleep(batch_delay)

        batch_start = batch_num * EMBEDDING_BATCH_SIZE
        batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(prepared))
        batch = prepared[batch_start:batch_end]

        batch_t0 = time.time()
        max_retries = 5
        for attempt in range(max_retries):
            try:
                docs, chunks, parquet_updates = _ingest_batch(batch, embeddings_model, client)
                break  # success
            except Exception as e:
                error_str = str(e)
                if ("RESOURCE_EXHAUSTED" in error_str or "429" in error_str) and attempt < max_retries - 1:
                    # Parse the API's retry delay (e.g., "retry in 7s") and use it directly
                    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str)
                    wait_secs = int(float(match.group(1))) + 1 if match else 30
                    # After any 429, set batch_delay to at least half the API's suggested retry time
                    # as the ongoing inter-batch pacing. Only increases, never decreases.
                    new_delay = max(batch_delay, wait_secs / 2)
                    batch_delay = new_delay
                    print(
                        f"   ⏳ Rate limited. Waiting {wait_secs}s, then pacing batches +{batch_delay:.1f}s each...",
                        flush=True,
                    )
                    time.sleep(wait_secs)
                    continue
                logger.warning(f"Batch {batch_num + 1}/{num_batches} failed: {e}")
                print(f"   ⚠ Batch {batch_num + 1}/{num_batches} failed: {e}")
                docs, chunks, parquet_updates = 0, 0, []
                break

        batch_elapsed = time.time() - batch_t0
        total_docs += docs
        total_chunks += chunks

        # Update parquet cache with new embeddings
        if parquet_updates:
            for df_idx, emb in parquet_updates:
                embedding_cache[df_idx] = emb
            embeddings_updated = True

        # Progress
        processed = batch_end
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (len(prepared) - processed) / rate if rate > 0 else 0
        embed_in_batch = sum(1 for p in batch if p["cached_embedding"] is None)

        print(
            f"   Batch {batch_num + 1}/{num_batches}: "
            f"{len(batch)} products ({embed_in_batch} embedded) in {batch_elapsed:.1f}s | "
            f"Total: {processed}/{len(prepared)} ({rate:.0f}/s, ETA {eta:.0f}s)",
            flush=True,
        )

        # Incremental checkpoint save — flush to disk every SAVE_INTERVAL batches
        if (batch_num + 1) % SAVE_INTERVAL == 0 and embedding_cache:
            _flush_embeddings_to_parquet(df, embedding_cache, sample_file)
            embedding_cache.clear()  # free memory — embeddings now stored in df["embedding"]
            embeddings_updated = False  # reset flag; final save only triggers if new work remains
            # Also flush OpenSearch index to consolidate segments
            try:
                client.indices.flush(index=OPENSEARCH_INDEX_NAME)
                print(f"   [checkpoint] Flushed OpenSearch index", flush=True)
            except Exception as e:
                logger.warning(f"Could not flush index: {e}")

    # Final save for any remaining embeddings not yet flushed
    if embeddings_updated and embedding_cache:
        _flush_embeddings_to_parquet(df, embedding_cache, sample_file)
    elif not embeddings_updated:
        print("   No new embeddings generated (all products used cached embeddings)", flush=True)

    # Refresh index
    client.indices.refresh(index=OPENSEARCH_INDEX_NAME)

    elapsed_total = time.time() - start_time
    print(f"   ✓ Ingested {total_docs} products ({total_chunks} chunks) in {elapsed_total:.1f}s")
    return total_docs, total_chunks


def show_stats():
    """Show current product statistics in OpenSearch."""
    try:
        client = create_opensearch_client()

        # Count total chunks in index
        count = client.count(index=OPENSEARCH_INDEX_NAME)["count"]

        # Count by collection using aggregation
        agg_body = {
            "size": 0,
            "aggs": {
                "collections": {
                    "terms": {"field": "collection_id", "size": 100}
                },
                "doc_types": {
                    "terms": {"field": "doc_type", "size": 100}
                },
                "unique_products": {
                    "cardinality": {"field": "product_id"}
                },
                "by_brand": {
                    "terms": {"field": "product_brand.keyword", "size": 20}
                },
            },
        }
        response = client.search(index=OPENSEARCH_INDEX_NAME, body=agg_body)

        print(f"\n📊 E-Commerce Product Statistics (OpenSearch index: {OPENSEARCH_INDEX_NAME}):")
        print(f"   Total chunks: {count}")

        unique_products = response["aggregations"]["unique_products"]["value"]
        print(f"   Unique products: {unique_products}")

        print("   By collection:")
        for bucket in response["aggregations"]["collections"]["buckets"]:
            print(f"      {bucket['key']}: {bucket['doc_count']} chunks")

        print("   By doc_type:")
        for bucket in response["aggregations"]["doc_types"]["buckets"]:
            print(f"      {bucket['key']}: {bucket['doc_count']} chunks")

        print("   Top 10 brands:")
        for bucket in response["aggregations"]["by_brand"]["buckets"][:10]:
            print(f"      {bucket['key']}: {bucket['doc_count']} chunks")

    except Exception as e:
        print(f"   ✗ Error fetching stats: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest ESCI products into OpenSearch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest_esci_products.py              # Ingest 10K sample (cached)
  python ingest_esci_products.py --limit 500  # Ingest 500 product sample
  python ingest_esci_products.py --resample   # Force re-sample
  python ingest_esci_products.py --all        # Ingest all US products
  python ingest_esci_products.py --stats      # Show index statistics
        """
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Number of products to sample (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--resample",
        action="store_true",
        help="Force re-sampling even if cached sample exists",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all US English products (no sampling)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current index statistics only",
    )
    parser.add_argument(
        "--reset-index",
        action="store_true",
        help="Delete the existing index before creating a new one (forces re-index with new mapping)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    try:
        if args.stats:
            show_stats()
        else:
            docs, chunks = ingest_esci_products(
                limit=args.limit,
                force_resample=args.resample,
                all_products=args.all,
                reset_index=args.reset_index,
            )
            print(f"\n✅ Successfully ingested {docs} ESCI products ({chunks} chunks)")
            show_stats()
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
