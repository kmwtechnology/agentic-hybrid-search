#!/bin/bash
# Agentic Hybrid Search Setup Script
# One-time setup: configure environment, start Docker services, ingest ESCI products

set -e  # Exit on error

echo "🚀 Agentic Hybrid Search - Local Setup"
echo ""

# Handle help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cat << EOF
Usage: ./scripts/setup.sh [OPTIONS]

One-time setup for local development: configures environment, starts Docker services, and ingests ESCI products.

OPTIONS:
    -h, --help          Show this help message and exit

REQUIREMENTS:
    - Docker (for PostgreSQL + OpenSearch containers)
    - Python 3.13 (creates .venv at project root if missing)
    - Node.js 18+ (for frontend)
    - Google API Key (for Gemini embeddings and LLM)
    - ~1.5 GB disk space (ESCI dataset + sample parquet + Docker volumes)
    - Internet access (to clone ESCI dataset repo from GitHub)

WHAT THIS SCRIPT DOES:
    1. Checks prerequisites (Docker, Python 3.13, Node.js)
    2. Clones ESCI dataset repo (if not present) → ../esci/
    3. Creates Python virtual environment at project root (if not present)
    4. Creates .env file and configures Google API key (if not present)
    5. Creates frontend .env configuration
    6. Installs Python dependencies in root .venv
    7. Installs Node.js frontend dependencies
    8. Starts PostgreSQL, OpenSearch, and OpenSearch Dashboards containers
    9. Initializes database and OpenSearch index
    10. Generates 10K deterministic product sample (seed=42)
    11. Generates embeddings and indexes products into OpenSearch

SERVICES STARTED:
    - PostgreSQL (checkpoint storage) → localhost:5432
    - OpenSearch (document search) → localhost:9200
    - OpenSearch Dashboards (visualization) → http://localhost:5601

REQUIREMENTS:
    GOOGLE_API_KEY must be set in .env file
    Get your key from: https://aistudio.google.com/apikey

NEXT STEPS after setup:
    1. Start backend: make dev-api (from langchain_agent/)
    2. Start frontend: make dev-web (from langchain_agent/)
    3. Visit http://localhost:5173

For more information, see README.md

EOF
    exit 0
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PARENT_DIR="$(dirname "$PROJECT_DIR")"

# 1. Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found"
    echo "   Please install Docker from https://www.docker.com/"
    exit 1
fi
echo "✓ Docker found"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    echo "   Please install Python 3.13 from https://www.python.org/"
    exit 1
fi

# Check Python version (must be 3.13)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 13 ]); then
    echo "❌ Python version too old: $PYTHON_VERSION"
    echo "   Required: Python 3.13 (or 3.13.x)"
    exit 1
fi

if [ "$PYTHON_MAJOR" -gt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -gt 13 ]); then
    echo "❌ Python version too new: $PYTHON_VERSION"
    echo "   Required: Python 3.13 (or 3.13.x)"
    echo "   LangChain/Pydantic are not compatible with Python 3.14+"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION found"

if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found"
    echo "   Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi
echo "✓ Node.js found"

echo ""

# 2. Setup ESCI dataset repository
echo "📦 Setting up ESCI dataset..."

ESCI_REPO_DIR="$PARENT_DIR/esci"
ESCI_FILE="$ESCI_REPO_DIR/shopping_queries_dataset/shopping_queries_dataset_products.parquet"

if [ ! -d "$ESCI_REPO_DIR" ]; then
    echo "   Cloning ESCI dataset from GitHub..."
    cd "$PARENT_DIR"
    git clone https://github.com/amazon-science/esci-data.git esci > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "   ✓ ESCI dataset cloned successfully"
    else
        echo "   ❌ Failed to clone ESCI dataset"
        echo "      GitHub: https://github.com/amazon-science/esci-data"
        echo "      Manual download: Extract shopping_queries_dataset/ to ../esci/"
        exit 1
    fi
    cd "$PROJECT_DIR"
else
    echo "✓ ESCI dataset directory exists"
fi

if [ -f "$ESCI_FILE" ]; then
    FILE_SIZE=$(du -h "$ESCI_FILE" | cut -f1)
    echo "✓ ESCI dataset file found ($FILE_SIZE)"
else
    echo "❌ ESCI dataset parquet file not found at:"
    echo "   $ESCI_FILE"
    echo "   Ensure shopping_queries_dataset_products.parquet is in: $ESCI_REPO_DIR/shopping_queries_dataset/"
    exit 1
fi
echo ""

# 3. Generate API key if .env doesn't exist
echo "📝 Configuring environment..."

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "   Creating .env file..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"

    # Generate API key
    API_KEY=$(openssl rand -hex 32)

    # Use sed to replace the placeholder (works on both macOS and Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/your-secure-api-key-here/$API_KEY/" "$PROJECT_DIR/.env"
    else
        sed -i "s/your-secure-api-key-here/$API_KEY/" "$PROJECT_DIR/.env"
    fi

    echo "   ✓ Generated API_KEY"

    # Prompt for Google API key
    echo ""
    echo "   🔑 Google API Key required for Gemini AI models"
    echo "   Get your key from: https://aistudio.google.com/apikey"
    echo ""
    read -rp "   Enter your GOOGLE_API_KEY: " GOOGLE_API_KEY_INPUT

    if [ -n "$GOOGLE_API_KEY_INPUT" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/your-google-api-key-here/$GOOGLE_API_KEY_INPUT/" "$PROJECT_DIR/.env"
        else
            sed -i "s/your-google-api-key-here/$GOOGLE_API_KEY_INPUT/" "$PROJECT_DIR/.env"
        fi
        echo "   ✓ GOOGLE_API_KEY configured"
    else
        echo "   ⚠ No key entered. Set GOOGLE_API_KEY in .env before running."
    fi
else
    # Extract existing API_KEY
    API_KEY=$(grep "^API_KEY=" "$PROJECT_DIR/.env" | cut -d'=' -f2)
    echo "   ✓ Using existing API_KEY"

    # Check if GOOGLE_API_KEY is still the placeholder
    EXISTING_GOOGLE_KEY=$(grep "^GOOGLE_API_KEY=" "$PROJECT_DIR/.env" | cut -d'=' -f2)
    if [ "$EXISTING_GOOGLE_KEY" = "your-google-api-key-here" ] || [ -z "$EXISTING_GOOGLE_KEY" ]; then
        echo ""
        echo "   🔑 Google API Key not yet configured"
        echo "   Get your key from: https://aistudio.google.com/apikey"
        echo ""
        read -rp "   Enter your GOOGLE_API_KEY: " GOOGLE_API_KEY_INPUT

        if [ -n "$GOOGLE_API_KEY_INPUT" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=$GOOGLE_API_KEY_INPUT/" "$PROJECT_DIR/.env"
            else
                sed -i "s/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=$GOOGLE_API_KEY_INPUT/" "$PROJECT_DIR/.env"
            fi
            echo "   ✓ GOOGLE_API_KEY configured"
        else
            echo "   ⚠ No key entered. Set GOOGLE_API_KEY in .env before running."
        fi
    else
        echo "   ✓ Using existing GOOGLE_API_KEY"
    fi
fi

# 3. Create frontend .env (if missing)
if [ ! -f "$PROJECT_DIR/web/.env" ]; then
    echo "   Creating web/.env..."
    cat > "$PROJECT_DIR/web/.env" << EOF
# Vite proxy in vite.config.ts routes /api and /ws to localhost:8000
# No VITE_API_URL needed for local dev (empty = relative URLs through proxy)
EOF
    echo "   ✓ Frontend env configured"
else
    echo "   ✓ Frontend env exists"
fi

echo ""

# 4. Create and setup root .venv
echo "📦 Python Virtual Environment..."

VENV_PATH="$PARENT_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "   Creating virtual environment at $PARENT_DIR/.venv..."
    python3 -m venv "$VENV_PATH"
    if [ $? -eq 0 ]; then
        echo "   ✓ Virtual environment created"
    else
        echo "   ❌ Failed to create virtual environment"
        exit 1
    fi
fi

source "$VENV_PATH/bin/activate"
pip install -q --upgrade pip setuptools wheel
pip install -q -r "$PROJECT_DIR/requirements.txt"
echo "✓ Python dependencies installed"
echo ""

# 5. Install frontend dependencies
echo "📦 Installing frontend dependencies..."

cd "$PROJECT_DIR/web"
if [ ! -d "node_modules" ]; then
    npm install --quiet
    echo "✓ Frontend dependencies installed"
else
    echo "✓ Frontend dependencies already installed"
fi
cd "$PROJECT_DIR"
echo ""

# Skip javadoc generation (ESCI products don't require it)
echo ""

# 8. Start Docker containers (PostgreSQL + OpenSearch)
echo "🐘 Starting Docker containers..."

cd "$PARENT_DIR"
if ! docker compose ps 2>/dev/null | grep -q "postgres.*Up"; then
    docker compose up -d postgres > /dev/null 2>&1
    echo "   Waiting for PostgreSQL to be ready..."
    sleep 3
    echo "✓ PostgreSQL started"
else
    echo "✓ PostgreSQL already running"
fi

if ! docker compose ps 2>/dev/null | grep -q "opensearch.*Up"; then
    docker compose up -d opensearch > /dev/null 2>&1
    echo "   Waiting for OpenSearch to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:9200/_cluster/health 2>/dev/null | grep -q '"status"'; then
            echo "✓ OpenSearch started"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "❌ OpenSearch failed to start within 30 seconds"
            echo "   Check: docker compose logs opensearch"
            exit 1
        fi
        sleep 2
    done
else
    echo "✓ OpenSearch already running"
fi

if ! docker compose ps 2>/dev/null | grep -q "opensearch-dashboards.*Up"; then
    docker compose up -d opensearch-dashboards > /dev/null 2>&1
    echo "   Waiting for OpenSearch Dashboards to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:5601/api/status 2>/dev/null | grep -q 'state'; then
            echo "✓ OpenSearch Dashboards started → http://localhost:5601"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "⚠ OpenSearch Dashboards is starting (may take a moment)"
            echo "   Access at: http://localhost:5601"
            break
        fi
        sleep 2
    done
else
    echo "✓ OpenSearch Dashboards already running → http://localhost:5601"
fi
cd "$PROJECT_DIR"
echo ""

# 9. Initialize database and OpenSearch index
echo "💾 Initializing database and OpenSearch..."

source "$PARENT_DIR/.venv/bin/activate"
cd "$PROJECT_DIR"

mkdir -p logs
PYTHONPATH=. python setup.py 2>&1 | tee logs/setup.log

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo ""
    echo "✓ Database and OpenSearch index initialized"
else
    echo ""
    echo "✗ Database initialization failed. Check logs/setup.log"
    exit 1
fi
echo ""

# 10. Generate 10K sample and ingest ESCI products
echo "🛍️  Preparing ESCI e-commerce products..."
echo "   Step 1: Create 10K deterministic sample (seed=42) → esci_products_sample_10000.parquet"
echo "   Step 2: Generate embeddings (~10K requests × 150 tokens = ~$0.30)"
echo "   Step 3: Index into OpenSearch"
echo ""

PYTHONPATH=. python ingest_esci_products.py 2>&1 | tee logs/ingest.log

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo ""
    SAMPLE_FILE="$PARENT_DIR/esci/shopping_queries_dataset/esci_products_sample_10000.parquet"
    if [ -f "$SAMPLE_FILE" ]; then
        SAMPLE_SIZE=$(du -h "$SAMPLE_FILE" | cut -f1)
        echo "✓ 10K product sample created: $SAMPLE_SIZE"
        echo "   Location: esci/shopping_queries_dataset/esci_products_sample_10000.parquet"
    fi
    echo "✓ ESCI products ingested and indexed successfully"
else
    echo ""
    echo "❌ Product ingestion failed. Check logs/ingest.log"
    echo "   You can retry later with: PYTHONPATH=. python ingest_esci_products.py"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Start backend:  cd langchain_agent && make dev-api"
echo "  2. Start frontend: cd langchain_agent && make dev-web"
echo "  3. Visit http://localhost:5173"
echo ""
echo "Services running at:"
echo "  • Backend API: http://localhost:8000"
echo "  • Frontend: http://localhost:5173"
echo "  • OpenSearch: http://localhost:9200"
echo "  • OpenSearch Dashboards: http://localhost:5601""
