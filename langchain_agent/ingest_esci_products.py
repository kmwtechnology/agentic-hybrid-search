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
EMBEDDING_BATCH_SIZE = 100  # Products per embedding API call


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
        FileNotFoundError: If main products parquet file not found
    """
    if not ESCI_PRODUCTS_FILE.exists():
        raise FileNotFoundError(f"ESCI products file not found: {ESCI_PRODUCTS_FILE}")

    sample_file = ESCI_DATASET_DIR / f"esci_products_sample_{limit}.parquet"

    # Return cached sample if it exists and not forcing resample
    if sample_file.exists() and not force_resample:
        logger.info(f"Loading cached sample from {sample_file.name}")
        df_sample = pd.read_parquet(sample_file)
        has_embeddings = "embedding" in df_sample.columns
        logger.info(f"  Products: {len(df_sample)}, Embeddings cached: {has_embeddings}")
        return df_sample

    # Load full dataset and filter to US English products
    logger.info(f"Loading products from {ESCI_PRODUCTS_FILE.name}...")
    df = pd.read_parquet(ESCI_PRODUCTS_FILE)

    logger.info(f"Total products: {len(df)}")

    # Filter to US English products only
    df_us = df[df["product_locale"] == PRODUCT_LOCALE].copy()
    logger.info(f"US products: {len(df_us)}")

    # Sample deterministically
    if limit < len(df_us):
        df_sample = df_us.sample(n=limit, random_state=42)
        logger.info(f"Sampled {limit} US products (deterministic, seed=42)")
    else:
        df_sample = df_us
        logger.info(f"Using all {len(df_us)} US products (limit {limit} >= dataset size)")

    # Initialize embedding column as None (will be populated during ingestion)
    df_sample["embedding"] = None

    # Cache the sample parquet for idempotent future runs
    ESCI_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df_sample.to_parquet(sample_file)
    logger.info(f"Cached sample to {sample_file.name}")

    return df_sample


def ensure_index_exists(client):
    """Create the OpenSearch index if it doesn't exist."""
    try:
        if not client.indices.exists(index=OPENSEARCH_INDEX_NAME):
            client.indices.create(index=OPENSEARCH_INDEX_NAME, body=INDEX_MAPPING)
            logger.info(f"Created index '{OPENSEARCH_INDEX_NAME}'")
        else:
            logger.info(f"Index '{OPENSEARCH_INDEX_NAME}' already exists")

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
    """Get set of product IDs already indexed in OpenSearch."""
    try:
        # Query for all unique product_ids in index
        query = {
            "size": 0,
            "aggs": {
                "product_ids": {
                    "terms": {"field": "product_id", "size": 100000}
                }
            }
        }
        response = client.search(index=OPENSEARCH_INDEX_NAME, body=query)
        product_ids = {bucket["key"] for bucket in response["aggregations"]["product_ids"]["buckets"]}
        logger.info(f"Found {len(product_ids)} products already indexed")
        return product_ids
    except Exception as e:
        logger.warning(f"Could not retrieve indexed product IDs: {e}")
        return set()


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


def ingest_esci_products(
    limit: int = DEFAULT_LIMIT,
    force_resample: bool = False,
    all_products: bool = False,
) -> Tuple[int, int]:
    """
    Ingest ESCI products into OpenSearch with batched embedding and verbose progress.

    Embeddings are generated in batches via embed_documents() (one API call per batch).
    Embeddings are cached in the sample parquet file to avoid regeneration.
    Products already indexed in OpenSearch are skipped.

    Args:
        limit: Number of products to sample (ignored if all_products=True)
        force_resample: If True, force re-sampling even if cached
        all_products: If True, ingest all US products (no sampling)

    Returns:
        Tuple of (total_products_ingested, total_chunks_created)
    """
    print("\n📦 Ingesting ESCI E-Commerce Products...")

    # Load or create sample
    if all_products:
        print(f"   Loading all US English products...")
        df = load_or_create_sample(limit=999999, force_resample=True)
    else:
        print(f"   Loading {limit} product sample...")
        df = load_or_create_sample(limit=limit, force_resample=force_resample)

    if df.empty:
        print("   ⚠️  No products loaded")
        return 0, 0

    # Initialize OpenSearch client
    client = create_opensearch_client()
    ensure_index_exists(client)

    # Check which products are already indexed
    indexed_ids = get_indexed_product_ids(client)
    products_to_ingest = [idx for idx, row in df.iterrows()
                          if str(row.get("product_id", "")) not in indexed_ids]

    if not products_to_ingest:
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
                    # Set inter-batch pacing: spread remaining batches across the rate limit window
                    # e.g., if rate limited after 37 batches in 46s, pace = 46/37 ≈ 1.2s + 25% buffer
                    elapsed_so_far = time.time() - start_time
                    batches_done = max(batch_num, 1)
                    batch_delay = (elapsed_so_far / batches_done) * 0.25
                    print(
                        f"   ⏳ Batch {batch_num + 1}/{num_batches}: rate limited, waiting {wait_secs}s "
                        f"(pacing future batches +{batch_delay:.1f}s)...",
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

    # Save updated embeddings back to parquet
    if embeddings_updated and embedding_cache:
        print(f"   Saving {len(embedding_cache)} new embeddings to parquet cache...", flush=True)
        # Ensure embedding column exists as object dtype
        if "embedding" not in df.columns:
            df["embedding"] = pd.Series([None] * len(df), index=df.index, dtype=object)
        # Write embeddings: use object array to avoid pandas list-broadcasting issue
        emb_series = df["embedding"].copy()
        for df_idx, emb in embedding_cache.items():
            emb_series.at[df_idx] = emb
        df["embedding"] = emb_series
        sample_file = ESCI_DATASET_DIR / f"esci_products_sample_{limit}.parquet"
        try:
            df.to_parquet(sample_file)
            print(f"   ✓ Cached {len(embedding_cache)} new embeddings to {sample_file.name}")
        except Exception as e:
            logger.warning(f"Could not save embeddings to parquet: {e}")

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
