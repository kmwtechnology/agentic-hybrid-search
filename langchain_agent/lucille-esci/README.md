# Lucille ESCI Configuration

> **Parent**: [langchain_agent/README.md](../README.md)

Maven module that configures the [Lucille](https://github.com/kmwtechnology/lucille) ETL framework
for ingesting Amazon ESCI products and relevance judgments into OpenSearch.

**This is not the Lucille source code.** It's a configuration package that wraps Lucille's Java
libraries with ESCI-specific field mappings, analyzers, and ingest pipelines.

## Directory Structure

```text
lucille-esci/
├── conf/              # HOCON pipeline configurations
│   ├── products.conf  # Product ingest: field mappings, chunking, embedding, collection_id
│   └── judgments.conf # Judgment ingest: relevance label mapping (E/S/C/I → 4.0/1.0/0.1/0.0)
├── mapping/           # OpenSearch field mappings and analyzers
│   ├── products.json  # Index template: knn_vector, text, keyword fields
│   └── judgments.json # Judgment index template
├── pom.xml            # Maven coordinates; references external Lucille version
└── target/            # Compiled artifacts (auto-generated)
```

## How It Works

1. **Lucille source** — external checkout at `LUCILLE_DIR` (default `~/github/kmwtechnology/lucille`)
2. **lucille-esci config** — this directory specifies field mappings and ETL rules
3. **lucille_ingest.sh** — orchestration script that:
   - Checks/builds `lucille-esci` + `lucille-bom` + `lucille-parquet` from the source tree
   - Reads `data/*.parquet` (precomputed embeddings, no API calls)
   - Applies `conf/*.conf` to transform records
   - Bulk-indexes into OpenSearch

## Configuration Files

### `conf/products.conf` (HOCON)

```hocon
ingestConf {
  processor {
    lucene {
      indexName = "agentic_hybrid_search_docs"
      analyzerName = "multilingual_analyzer"
    }
  }
  
  globalFieldConfig {
    knn_vector.dimension = 768
  }
  
  documentFields {
    product_id     { type = "text" }
    product_title  { type = "text"; copy_to = ["title_suggest"] }
    knn_vector     { type = "knn_vector"; dimension = 768 }
  }
  
  # CRITICAL: collection_id is required on EVERY product doc
  # See main.py for collection_id-based filtering
  defaultFields {
    collection_id = "esci_products"
  }
}
```

**Key points:**
- `title_suggest` and `brand_suggest` are **edge-ngram** fields required by `/api/suggest` typeahead
- `collection_id=esci_products` is set on every document (checked by all retrieval queries)
- `knn_vector.dimension = 768` matches `VECTOR_DIMENSION` in `.env`

### `conf/judgments.conf` (HOCON)

Maps ESCI relevance labels to numeric scores:
- `E` (Exact) → `4.0`
- `S` (Substitute) → `1.0`
- `C` (Complement) → `0.1`
- `I` (Irrelevant) → `0.0`

Lookups via `OpenSearchVectorStore.lookup_judgments(query)` — exact keyword match on `query.keyword`.

### `mapping/products.json` (OpenSearch mappings)

Field definitions for the product index:
- `knn_vector` — HNSW index, 768-dim
- `product_title`, `product_brand`, `product_color` — text + keyword dual mapping (faceting)
- `title_suggest`, `brand_suggest` — edge-ngram analyzers for prefix matching

## Versioning

**CRITICAL:** Keep these in sync:

1. `lucille-esci/pom.xml`:
   ```xml
   <lucille.version>1.0.0-SNAPSHOT</lucille.version>
   ```

2. `scripts/lucille_ingest.sh`:
   ```bash
   LUCILLE_VERSION="1.0.0-SNAPSHOT"
   ```

When the external Lucille repo's version bumps, update both files **in the same commit**.

## Running Lucille Ingest

### Standard (default 10 k sample)

```bash
# From langchain_agent/:
bash scripts/lucille_ingest.sh
```

- Reads `data/esci_products_sample_10000.parquet` (9,618 docs + embeddings)
- Reads `data/esci_judgments_aggregated.parquet` (97,345 queries)
- No embedding API calls needed (embeddings precomputed in parquet)
- ~30 s total

### With reset (atomically recreates index)

```bash
bash scripts/lucille_ingest.sh --reset-index
```

Deletes the index via Python's `setup.py --reset-index` first, preventing a race where Lucille
auto-creates a broken default-mapped index between a curl DELETE and the ingest's first write.

### Skip judgments

```bash
bash scripts/lucille_ingest.sh --skip-judgments
```

Ingests products only.

## Environment Setup

`lucille_ingest.sh` auto-detects Java/Maven and Lucille checkout:

```bash
# Check prerequisites
java -version          # Java 17+
mvn -version           # Maven 3.8+
ls ~/github/kmwtechnology/lucille  # Lucille source (or set LUCILLE_DIR)
```

## Troubleshooting

**Java not found:**
```bash
brew install openjdk@17
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
```

**Maven build fails:**
```bash
mvn clean install -DskipTests
```

**OpenSearch DSN wrong:**
```bash
# lucille_ingest.sh loads .env; check:
grep OPENSEARCH_HOST .env
grep OPENSEARCH_PORT .env
```

**Collection_id missing:**
Check `conf/products.conf` — every product doc must have `collection_id=esci_products` set
in `defaultFields`. If products are indexed without it, retrieval queries won't find them.

## References

- [Lucille Framework](https://github.com/kmwtechnology/lucille)
- [OpenSearch field mappings](https://opensearch.org/docs/latest/im-plugin/index-templates/)
- [HNSW KNN](https://opensearch.org/docs/latest/search-plugins/knn/knn-index/)
