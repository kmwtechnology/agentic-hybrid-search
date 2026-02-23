#!/usr/bin/env python3
"""
ESCI Product Embedding Generation Script

Generates embeddings for all unique US ESCI products and saves them to parquet.
Focuses purely on embedding generation with incremental checkpoints.
This is a separate step from OpenSearch ingestion.

Usage:
    python generate_embeddings.py              # Generate all US product embeddings
    python generate_embeddings.py --resample   # Force re-read source and regenerate
    python generate_embeddings.py --stats      # Show embedding cache stats
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import (
    EMBEDDINGS_MODEL,
    VECTOR_DIMENSION,
)

logger = logging.getLogger(__name__)

# Path to ESCI dataset
BASE_DIR = Path(__file__).parent
ESCI_DATASET_DIR = BASE_DIR.parent / "esci" / "shopping_queries_dataset"
ESCI_PRODUCTS_FILE = ESCI_DATASET_DIR / "shopping_queries_dataset_products.parquet"
FULL_US_PARQUET = ESCI_DATASET_DIR / "esci_products_full_us.parquet"

# Embedding parameters
PRODUCT_LOCALE = "us"
EMBEDDING_BATCH_SIZE = 100  # Match Gemini API's optimal batch size (25-30 products per internal request)
SAVE_INTERVAL = 50  # Save checkpoint every N batches (~5K products at 100/batch)


def load_or_create_full_us_dataset(force_resample: bool = False) -> pd.DataFrame:
    """Load or create the full deduplicated US product dataset."""
    # Return cached if it exists and not forcing resample
    if FULL_US_PARQUET.exists() and not force_resample:
        logger.info(f"Loading cached full US dataset from {FULL_US_PARQUET.name}")
        df = pd.read_parquet(FULL_US_PARQUET)
        has_embeddings = "embedding" in df.columns and df["embedding"].notna().any()
        logger.info(f"  Products: {len(df):,}, Embeddings cached: {has_embeddings}")
        return df

    # Load and deduplicate
    logger.info(f"Loading products from {ESCI_PRODUCTS_FILE.name}...")
    df = pd.read_parquet(ESCI_PRODUCTS_FILE)
    logger.info(f"Total products: {len(df):,}")

    # Filter to US English only
    df_us = df[df["product_locale"] == PRODUCT_LOCALE].copy()
    logger.info(f"US products: {len(df_us):,}")

    # Deduplicate by product_id
    df_dedup = df_us.drop_duplicates(subset=["product_id"], keep="first").copy()
    dups_removed = len(df_us) - len(df_dedup)
    if dups_removed > 0:
        logger.info(f"Deduplicated: removed {dups_removed:,} duplicate product_ids")

    # Initialize embedding column
    df_dedup["embedding"] = None

    # Cache for future runs
    ESCI_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df_dedup.to_parquet(FULL_US_PARQUET)
    logger.info(f"Cached full US dataset to {FULL_US_PARQUET.name}")

    return df_dedup


def _prepare_product_text(row) -> Optional[str]:
    """Extract and concatenate product text fields."""
    title = str(row.get("product_title", ""))
    description = str(row.get("product_description", ""))
    bullet_points = str(row.get("product_bullet_point", ""))

    text = "\n".join([t for t in [title, description, bullet_points] if t and str(t).strip()])
    return text if text and len(text) >= 50 else None


def _flush_embeddings_to_parquet(df: pd.DataFrame, embedding_cache: dict, parquet_file: Path) -> None:
    """Write pending embeddings to parquet and clear cache."""
    if not embedding_cache:
        return

    if "embedding" not in df.columns:
        df["embedding"] = pd.Series([None] * len(df), index=df.index, dtype=object)

    for df_idx, emb in embedding_cache.items():
        df.at[df_idx, "embedding"] = emb

    try:
        df.to_parquet(parquet_file)
        print(f"   [checkpoint] Saved {len(embedding_cache):,} embeddings → {parquet_file.name}", flush=True)
    except Exception as e:
        logger.warning(f"Could not save embeddings to parquet: {e}")


def generate_embeddings(force_resample: bool = False) -> int:
    """
    Generate embeddings for all unique US ESCI products.

    Args:
        force_resample: If True, force re-read source parquet

    Returns:
        Number of embeddings generated
    """
    print("\n📊 Generating ESCI Product Embeddings...")

    # Load dataset
    df = load_or_create_full_us_dataset(force_resample=force_resample)
    if df.empty:
        print("   ⚠️  No products loaded")
        return 0

    # Prepare product texts
    print(f"   Preparing {len(df):,} product texts...")
    prepared = []
    skipped = 0
    for idx, row in df.iterrows():
        text = _prepare_product_text(row)
        if text:
            prepared.append((idx, text))
        else:
            skipped += 1

    print(f"   Prepared {len(prepared):,} products ({skipped:,} skipped for insufficient text)")

    # Count cached vs need-to-embed
    cached_count = sum(1 for idx, _ in prepared if df.at[idx, "embedding"] is not None)
    need_embed_count = len(prepared) - cached_count

    if need_embed_count == 0:
        print(f"   ✓ All {len(prepared):,} products already have embeddings cached")
        return 0

    print(f"   Embedding {need_embed_count:,} new products ({cached_count:,} already cached)...")

    # Initialize embeddings model
    embeddings_model = GoogleGenerativeAIEmbeddings(
        model=EMBEDDINGS_MODEL,
        output_dimensionality=VECTOR_DIMENSION,
    )

    # Process in batches
    embedding_cache = {}
    total_embedded = 0
    start_time = time.time()
    num_batches = (need_embed_count + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
    batch_delay = 0.0

    for batch_num in range(num_batches):
        # Pace requests
        if batch_delay > 0 and batch_num > 0:
            time.sleep(batch_delay)

        # Collect batch
        batch_start = batch_num * EMBEDDING_BATCH_SIZE
        batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, need_embed_count)
        batch_items = prepared[batch_start:batch_end]

        # Filter to items without cached embeddings
        texts_to_embed = []
        indices_to_embed = []
        for df_idx, text in batch_items:
            if df.at[df_idx, "embedding"] is None:
                texts_to_embed.append(text)
                indices_to_embed.append(df_idx)

        batch_t0 = time.time()
        embeddings = []
        max_retries = 5

        for attempt in range(max_retries):
            try:
                embeddings = embeddings_model.embed_documents(texts_to_embed)
                break  # success
            except Exception as e:
                error_str = str(e)
                if ("RESOURCE_EXHAUSTED" in error_str or "429" in error_str) and attempt < max_retries - 1:
                    # Parse retry delay and increase pacing
                    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str)
                    wait_secs = int(float(match.group(1))) + 1 if match else 30
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
                break

        batch_elapsed = time.time() - batch_t0

        # Store embeddings in cache
        if embeddings:
            for df_idx, emb in zip(indices_to_embed, embeddings):
                embedding_cache[df_idx] = emb
            total_embedded += len(embeddings)

        # Progress
        elapsed = time.time() - start_time
        rate = total_embedded / elapsed if elapsed > 0 else 0
        eta = (need_embed_count - total_embedded) / rate if rate > 0 else 0

        print(
            f"   Batch {batch_num + 1}/{num_batches}: "
            f"{len(texts_to_embed)} embedded in {batch_elapsed:.1f}s | "
            f"Total: {total_embedded}/{need_embed_count} ({rate:.0f}/s, ETA {eta:.0f}s)",
            flush=True,
        )

        # Incremental checkpoint
        if (batch_num + 1) % SAVE_INTERVAL == 0 and embedding_cache:
            _flush_embeddings_to_parquet(df, embedding_cache, FULL_US_PARQUET)
            embedding_cache.clear()

    # Final save
    if embedding_cache:
        _flush_embeddings_to_parquet(df, embedding_cache, FULL_US_PARQUET)

    elapsed_total = time.time() - start_time
    print(f"   ✓ Generated {total_embedded:,} embeddings in {elapsed_total:.1f}s ({total_embedded/elapsed_total:.0f}/s)")
    return total_embedded


def show_stats():
    """Show embedding cache statistics."""
    if not FULL_US_PARQUET.exists():
        print(f"   No cached embeddings found at {FULL_US_PARQUET.name}")
        return

    df = pd.read_parquet(FULL_US_PARQUET)
    cached = df["embedding"].notna().sum() if "embedding" in df.columns else 0

    print(f"\n📊 Embedding Cache Statistics:")
    print(f"   Total products: {len(df):,}")
    print(f"   With embeddings: {cached:,}")
    print(f"   Without embeddings: {len(df) - cached:,}")
    print(f"   Completion: {100*cached/len(df):.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings for all US ESCI products",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_embeddings.py              # Generate all embeddings
  python generate_embeddings.py --resample   # Force re-read and regenerate
  python generate_embeddings.py --stats      # Show cache stats
        """
    )
    parser.add_argument(
        "--resample",
        action="store_true",
        help="Force re-read source parquet and regenerate",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show embedding cache statistics only",
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
            count = generate_embeddings(force_resample=args.resample)
            print(f"\n✅ Generated {count:,} embeddings")
            show_stats()
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
