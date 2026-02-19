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
import logging
import sys
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


def ingest_product(
    product_id: str,
    title: str,
    description: str,
    bullet_points: str,
    brand: str,
    color: str,
    locale: str,
    cached_embedding: Optional[List[float]],
    embeddings: GoogleGenerativeAIEmbeddings,
    client=None,
) -> Tuple[int, int, Optional[List[float]]]:
    """
    Ingest a single product into OpenSearch.

    Each chunk becomes a standalone OpenSearch document.
    Uses cached embedding if available, otherwise generates new one.

    Args:
        product_id: Unique product identifier
        title: Product title
        description: Product description
        bullet_points: Product bullet points (concatenated with \n)
        brand: Product brand
        color: Product color
        locale: Product locale (e.g., "us")
        cached_embedding: Pre-generated embedding (from parquet) or None
        embeddings: Embeddings model instance
        client: OpenSearch client instance

    Returns:
        Tuple of (docs_inserted, chunks_inserted, generated_embedding or None)
    """
    # Concatenate product text
    chunk_text_content = "\n".join(
        [t for t in [title, description, bullet_points] if t and str(t).strip()]
    )

    # Skip if combined text is too short
    if not chunk_text_content or len(chunk_text_content) < 50:
        return 0, 0, None

    try:
        # Products are indexed as whole units (no chunking) per CHUNKING_STRATEGY
        strategy = CHUNKING_STRATEGY.get(ESCI_COLLECTION_NAME, {})
        if strategy.get("enabled", False):
            chunks = chunk_text(chunk_text_content)
        else:
            chunks = [chunk_text_content]
        actions = []
        generated_embedding = None

        base_fields = {
            "document_id": product_id,
            "collection_id": ESCI_COLLECTION_NAME,
            "source": "esci/shopping_queries_dataset",
            "title": title,
            "doc_type": "product",
            "product_id": product_id,
            "product_brand": brand,
            "product_color": color,
            "product_locale": locale,
        }

        for chunk_idx, chunk in enumerate(chunks):
            # Use cached embedding if available, otherwise generate
            if cached_embedding is not None and isinstance(cached_embedding, list):
                chunk_embedding = cached_embedding
            else:
                chunk_embedding = embeddings.embed_query(chunk)
                if chunk_idx == 0:  # Save first chunk's embedding for parquet
                    generated_embedding = chunk_embedding

            doc = {
                **base_fields,
                "chunk_index": chunk_idx,
                "chunk_text": chunk,
                "embedding": chunk_embedding,
            }
            actions.append({
                "_index": OPENSEARCH_INDEX_NAME,
                "_id": f"{product_id}-{chunk_idx}",
                "_source": doc,
            })

        if actions and client:
            success, errors = os_helpers.bulk(client, actions, refresh=False)
            if errors:
                logger.warning(f"Bulk ingestion errors for product '{product_id}': {errors}")
            return 1, len(actions), generated_embedding

        return 0, 0, generated_embedding

    except Exception as e:
        logger.warning(f"Error ingesting product '{product_id}': {e}")
        return 0, 0, None


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


def ingest_esci_products(
    limit: int = DEFAULT_LIMIT,
    force_resample: bool = False,
    all_products: bool = False,
) -> Tuple[int, int]:
    """
    Ingest ESCI products into OpenSearch with embedding caching.

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
        df = load_or_create_sample(limit=999999, force_resample=True)  # Load all
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

    print(f"   Processing {len(products_to_ingest)}/{len(df)} new products...")

    # Initialize embeddings
    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDINGS_MODEL,
        output_dimensionality=VECTOR_DIMENSION,
    )

    total_docs = 0
    total_chunks = 0
    embeddings_updated = False

    # Ingest each product
    for count, idx in enumerate(products_to_ingest, 1):
        try:
            row = df.loc[idx]
            product_id = str(row.get("product_id", ""))
            title = str(row.get("product_title", ""))
            description = str(row.get("product_description", ""))
            bullet_points = str(row.get("product_bullet_point", ""))
            brand = str(row.get("product_brand", ""))
            color = str(row.get("product_color", ""))
            locale = str(row.get("product_locale", "us"))

            # Use cached embedding if available
            cached_embedding = row.get("embedding")
            if cached_embedding is not None and isinstance(cached_embedding, (list, str)):
                # If it's a string (JSON), parse it
                if isinstance(cached_embedding, str):
                    import json
                    try:
                        cached_embedding = json.loads(cached_embedding)
                    except:
                        cached_embedding = None

            docs, chunks, generated_embedding = ingest_product(
                product_id=product_id,
                title=title,
                description=description,
                bullet_points=bullet_points,
                brand=brand,
                color=color,
                locale=locale,
                cached_embedding=cached_embedding,
                embeddings=embeddings,
                client=client,
            )

            # Update parquet if new embedding was generated
            if generated_embedding is not None and cached_embedding is None:
                df.at[idx, "embedding"] = generated_embedding
                embeddings_updated = True

            total_docs += docs
            total_chunks += chunks

            if count % 500 == 0:
                print(f"      Processed {count}/{len(products_to_ingest)} new products...")

        except Exception as e:
            logger.warning(f"Error processing product at row {idx}: {e}")
            continue

    # Save updated embeddings back to parquet
    if embeddings_updated:
        sample_file = ESCI_DATASET_DIR / f"esci_products_sample_{limit}.parquet"
        try:
            df.to_parquet(sample_file)
            logger.info(f"Saved embeddings to {sample_file.name}")
            print(f"   ✓ Cached embeddings for future runs")
        except Exception as e:
            logger.warning(f"Could not save embeddings to parquet: {e}")

    # Refresh index to make all documents searchable
    client.indices.refresh(index=OPENSEARCH_INDEX_NAME)

    print(f"   ✓ Ingested {total_docs} products ({total_chunks} chunks)")
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
                    "terms": {"field": "product_brand", "size": 20}
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
