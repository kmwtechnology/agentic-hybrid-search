# Stage 1: Build React frontend (context is repo root, so use langchain_agent/web/)
FROM node:20-slim AS frontend-builder

WORKDIR /app/web

COPY langchain_agent/web/package.json langchain_agent/web/package-lock.json* ./
RUN npm ci

COPY langchain_agent/web/ ./
# Use empty VITE_API_URL so production builds use relative URLs (same-domain requests)
RUN VITE_API_URL="" npm run build

# Stage 2: Python application
FROM python:3.13-slim AS runtime

# Install system dependencies for psycopg binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (context is repo root, so prefix with langchain_agent/)
COPY langchain_agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (context is repo root, so prefix with langchain_agent/)
COPY langchain_agent/*.py ./
COPY langchain_agent/api/ ./api/

# Create ESCI dataset directory and copy 10K sample with pre-computed embeddings.
#
# Path must match ingest_esci_products.py: that module computes
# `BASE_DIR.parent / "esci" / "shopping_queries_dataset"` where BASE_DIR is
# /app (WORKDIR). So the dataset must live at /esci/shopping_queries_dataset
# — not /app/esci — or the ingest falls back to looking for the full ~1.8M
# parquet (which is intentionally not shipped) and fails with FileNotFoundError.
RUN mkdir -p /esci/shopping_queries_dataset
COPY esci/shopping_queries_dataset/esci_products_sample_10000.parquet /esci/shopping_queries_dataset/

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/web/dist ./web/dist

# Set Python path so imports resolve from /app
ENV PYTHONPATH=/app

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
