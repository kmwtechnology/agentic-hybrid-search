#!/usr/bin/env bash
# lucille_ingest.sh — Ingest ESCI products and judgments into OpenSearch using Lucille ETL
#
# Steps:
#   1. Install Lucille plugins to local Maven repo (skipped if already installed)
#   2. Build the lucille/esci module (skipped if JAR is up-to-date)
#   3. Pre-aggregate judgments parquet (skipped if output already exists)
#   4. Run Lucille products ingest (ParquetConnector → OpenSearch)
#   5. Run Lucille judgments ingest (ParquetConnector → OpenSearch)
#
# Required env vars (sourced from langchain_agent/.env):
#   OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_INDEX_NAME
#   ESCI_DATASET_DIR
#
# Optional:
#   LUCILLE_THREADS (default: 2) — worker threads per pipeline

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$(dirname "$AGENT_DIR")"
LUCILLE_DIR="$REPO_DIR/lucille"
ESCI_MODULE_DIR="$AGENT_DIR/lucille-esci"

# ── Colour helpers ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[lucille_ingest]${NC} $*"; }
warn()  { echo -e "${YELLOW}[lucille_ingest]${NC} $*"; }
error() { echo -e "${RED}[lucille_ingest] ERROR:${NC} $*" >&2; }

# ── Load .env ────────────────────────────────────────────────────────────────
ENV_FILE="$AGENT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    # Strip inline comments and surrounding quotes
    value="${value%%#*}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value#\"}" ; value="${value%\"}"
    value="${value#\'}" ; value="${value%\'}"
    export "$key=$value"
  done < <(grep -v '^#' "$ENV_FILE" | grep -v '^$' | grep '=')
fi

# ── Defaults ─────────────────────────────────────────────────────────────────
OPENSEARCH_HOST="${OPENSEARCH_HOST:-localhost}"
OPENSEARCH_PORT="${OPENSEARCH_PORT:-9200}"
OPENSEARCH_SCHEME="${OPENSEARCH_USE_SSL:-false}"
if [[ "$OPENSEARCH_SCHEME" == "true" ]]; then
  OPENSEARCH_URL="https://${OPENSEARCH_HOST}:${OPENSEARCH_PORT}"
else
  OPENSEARCH_URL="http://${OPENSEARCH_HOST}:${OPENSEARCH_PORT}"
fi
OPENSEARCH_INDEX="${OPENSEARCH_INDEX_NAME:-agentic_hybrid_search_docs}"
DATA_DIR="$REPO_DIR/data"
# Raw ESCI dataset (external clone, not tracked in git)
ESCI_DIR="${ESCI_DATASET_DIR:-$REPO_DIR/esci/shopping_queries_dataset}"
LUCILLE_VERSION="0.9.0-SNAPSHOT"

# ── Prerequisite checks ──────────────────────────────────────────────────────
if ! command -v java &>/dev/null; then
  error "Java not found. Install Java 17+ (brew install openjdk@17)."
  exit 1
fi
if ! command -v mvn &>/dev/null; then
  error "Maven not found. Install with: brew install maven"
  exit 1
fi

JAVA_VER=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d. -f1)
if [[ "$JAVA_VER" -lt 17 ]]; then
  error "Java 17+ required, found: $JAVA_VER"
  exit 1
fi

# ── Step 1: Install Lucille plugins to local Maven repo ──────────────────────
PARQUET_JAR=~/.m2/repository/com/kmwllc/lucille-parquet/${LUCILLE_VERSION}/lucille-parquet-${LUCILLE_VERSION}.jar
if [[ ! -f "$PARQUET_JAR" ]]; then
  info "Installing Lucille plugins to local Maven repo..."
  if [[ ! -d "$LUCILLE_DIR/lucille-plugins" ]]; then
    error "Lucille source not found at $LUCILLE_DIR"
    error "Run: curl -sL https://github.com/kmwtechnology/lucille/archive/refs/tags/0.9.0.tar.gz | tar -xz -C $REPO_DIR && mv $REPO_DIR/lucille-0.9.0 $LUCILLE_DIR"
    exit 1
  fi
  (cd "$LUCILLE_DIR" && mvn install -pl lucille-plugins/lucille-parquet -am -q -DskipTests)
  info "Lucille plugins installed."
else
  info "Lucille parquet plugin already in local Maven repo."
fi

# ── Step 2: Build lucille/esci module ────────────────────────────────────────
ESCI_JAR="$ESCI_MODULE_DIR/target/lucille-esci-1.0.0.jar"
# Rebuild if pom.xml or any conf file is newer than the JAR
NEEDS_BUILD=false
if [[ ! -f "$ESCI_JAR" ]]; then
  NEEDS_BUILD=true
else
  for f in "$ESCI_MODULE_DIR/pom.xml" "$ESCI_MODULE_DIR/conf/"*.conf; do
    if [[ "$f" -nt "$ESCI_JAR" ]]; then
      NEEDS_BUILD=true
      break
    fi
  done
fi

if [[ "$NEEDS_BUILD" == "true" ]]; then
  info "Building lucille/esci Maven module..."
  (cd "$ESCI_MODULE_DIR" && mvn package -q -DskipTests)
  info "Build complete."
else
  info "lucille/esci JAR is up-to-date."
fi

# ── Step 3: Pre-aggregate judgments parquet ──────────────────────────────────
JUDGMENTS_PARQUET="$DATA_DIR/esci_judgments_aggregated.parquet"
if [[ ! -f "$JUDGMENTS_PARQUET" ]]; then
  info "Pre-aggregating ESCI judgments (2.6M rows → ~97k per-query rows)..."
  PYTHON="${AGENT_DIR}/.venv/bin/python"
  if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
  fi
  "$PYTHON" "$SCRIPT_DIR/prepare_judgments_parquet.py" --locale us
  info "Judgments parquet ready."
else
  info "Judgments parquet already exists: $JUDGMENTS_PARQUET"
fi

# ── Step 4: Run products ingest ───────────────────────────────────────────────
PRODUCTS_PARQUET="$DATA_DIR/esci_products_sample_10000.parquet"
if [[ ! -f "$PRODUCTS_PARQUET" ]]; then
  error "Products parquet not found: $PRODUCTS_PARQUET"
  exit 1
fi

info "Running Lucille products ingest..."
info "  Source: $PRODUCTS_PARQUET"
info "  Target: $OPENSEARCH_URL/$OPENSEARCH_INDEX"

PARQUET_PATH="$PRODUCTS_PARQUET" \
OPENSEARCH_URL="$OPENSEARCH_URL" \
OPENSEARCH_INDEX="$OPENSEARCH_INDEX" \
  java \
    -Dconfig.file="$ESCI_MODULE_DIR/conf/products.conf" \
    -cp "$ESCI_MODULE_DIR/target/lib/*:$ESCI_MODULE_DIR/target/lucille-esci-1.0.0.jar" \
    com.kmwllc.lucille.core.Runner

info "Products ingest complete."

# ── Step 5: Run judgments ingest ──────────────────────────────────────────────
info "Running Lucille judgments ingest..."
info "  Source: $JUDGMENTS_PARQUET"
info "  Target: ${OPENSEARCH_URL}/esci_judgments"

JUDGMENTS_PARQUET_PATH="$JUDGMENTS_PARQUET" \
OPENSEARCH_URL="$OPENSEARCH_URL" \
  java \
    -Dconfig.file="$ESCI_MODULE_DIR/conf/judgments.conf" \
    -cp "$ESCI_MODULE_DIR/target/lib/*:$ESCI_MODULE_DIR/target/lucille-esci-1.0.0.jar" \
    com.kmwllc.lucille.core.Runner

info "Judgments ingest complete."
info "All done. Products → $OPENSEARCH_INDEX | Judgments → esci_judgments"
