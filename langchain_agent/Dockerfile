# Stage 1: Build React frontend (context is repo root, so use langchain_agent/web/)
FROM node:24-slim AS frontend-builder

WORKDIR /app/web

COPY langchain_agent/web/package.json langchain_agent/web/package-lock.json* ./
RUN npm ci

COPY langchain_agent/web/ ./
# Use empty VITE_API_URL so production builds use relative URLs (same-domain requests)
RUN VITE_API_URL="" npm run build

# Stage 2: Python application
FROM python:3.14-slim AS runtime

# Install system dependencies for psycopg binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (context is repo root, so prefix with langchain_agent/)
COPY langchain_agent/requirements.txt ./
# Install CPU-only torch before requirements.txt so sentence-transformers reuses it.
# Cloud Run is CPU-only; the default PyPI torch wheel bundles ~2GB of CUDA libraries
# that are never used. The CPU wheel cuts the pip layer from ~3GB to ~750MB.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (context is repo root, so prefix with langchain_agent/)
COPY langchain_agent/*.py ./
COPY langchain_agent/api/ ./api/

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/web/dist ./web/dist

# Set Python path so imports resolve from /app
ENV PYTHONPATH=/app

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
