# Deployment Testing Guide

Comprehensive testing suite for validating Agentic Hybrid Search deployments. Includes post-deployment smoke tests, Cloud Run-specific validation, and data integrity checks.

## Quick Start

### Local Testing (Against Localhost)

```bash
# Run all smoke tests against local deployment
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -v -m "e2e and slow"

# Run Cloud Run-specific tests
PYTHONPATH=. pytest tests/e2e/test_cloud_run_deployment.py -v -m "e2e and slow"

# Run data integrity tests
PYTHONPATH=. pytest tests/e2e/test_deployment_data.py -v -m "e2e and slow"
```

### Cloud Run Testing

```bash
# Set Cloud Run URL
export CLOUD_RUN_URL="https://agentic-hybrid-search-xyz.us-central1.run.app"

# Run tests against Cloud Run
PYTHONPATH=. pytest tests/e2e/ -v -m "e2e and slow"
```

### Bash Smoke Test Script

Quick validation without pytest:

```bash
# Local testing
./scripts/smoke_test.sh http://localhost:8000

# Cloud Run testing
./scripts/smoke_test.sh https://agentic-hybrid-search-xyz.us-central1.run.app

# With custom API key
API_KEY=your-api-key ./scripts/smoke_test.sh https://your-deployment-url
```

## Test Files

### 1. `test_deployment_smoke.py` (94 lines, 13 tests)

Post-deployment validation of core functionality.

**Tests:**
- **Health Checks** — `/api/health` endpoint validation
  - Status field (ok/degraded)
  - Version information
  - PostgreSQL connectivity
  - Google AI API availability
  - OpenSearch status
  - Product document count

- **Authentication** — API key validation
  - Valid API key acceptance
  - Invalid API key rejection
  - Missing API key rejection

- **WebSocket Connectivity** — Real-time chat validation
  - WebSocket connection acceptance
  - ConnectionEstablished event on connect
  - Message reception and processing

- **Search Pipeline** — RAG Q&A functionality
  - Search intent returns results
  - Comparison intent between products
  - Refinement intent constrains results
  - Citations include product URLs

- **Response Timing** — Performance validation
  - Search responses < 5 seconds (+ network overhead)
  - Generation responses < 10 seconds (+ network overhead)

**Usage:**
```bash
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -v

# Run specific test
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestDeploymentHealth::test_health_endpoint_returns_ok -v

# Run by marker
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -m "e2e" -v
```

### 2. `test_cloud_run_deployment.py` (87 tests)

Cloud Run-specific validation including HTTPS, scaling, and environment configuration.

**Tests:**
- **Connectivity** — Service discovery and HTTPS
  - Service responds to requests
  - HTTPS certificate validation
  - Cloud Run URL environment variable

- **Request Timeout** — Timeout handling under Cloud Run's 1-hour limit
  - Requests complete within limits
  - WebSocket maintains connection

- **Graceful Shutdown** — SIGTERM signal handling
  - Health checks remain available
  - In-flight requests complete gracefully

- **Horizontal Scaling** — Concurrent request handling
  - Health checks under concurrent load
  - Multiple concurrent WebSocket connections
  - Burst request handling (20 requests)

- **Logging** — Cloud Logging integration
  - JSON logging format validation

- **Environment Configuration** — Secret Manager integration
  - Environment variables loaded correctly
  - No hardcoded credentials in responses
  - API key from Secret Manager

- **Database** — Connection pool validation
  - Connection pool initialized
  - Checkpoint table exists

- **OpenSearch** — Index and data validation
  - Index is accessible
  - Product documents indexed

**Usage:**
```bash
CLOUD_RUN_URL="https://your-deployment" PYTHONPATH=. pytest tests/e2e/test_cloud_run_deployment.py -v

# Run scaling tests only
PYTHONPATH=. pytest tests/e2e/test_cloud_run_deployment.py::TestHorizontalScaling -v
```

### 3. `test_deployment_data.py` (92 tests)

Data integrity and search functionality validation.

**Tests:**
- **Product Indexing** — ESCI product data validation
  - Products indexed in vector store
  - Document count within reasonable range
  - Hybrid search returns products
  - Vector search semantic similarity
  - Lexical search exact match

- **Product Metadata** — Metadata completeness
  - Required metadata fields present
  - Brand attribute accessible and searchable

- **Data Consistency** — Integrity validation
  - Same query returns consistent results
  - No data corruption after deployment

- **Checkpoint Persistence** — LangGraph state management
  - Conversation checkpoints stored
  - Context maintained across messages

**Usage:**
```bash
CLOUD_RUN_URL="https://your-deployment" PYTHONPATH=. pytest tests/e2e/test_deployment_data.py -v

# Run indexing tests only
PYTHONPATH=. pytest tests/e2e/test_deployment_data.py::TestESCIProductIndexing -v
```

## Bash Smoke Test Script

Location: `langchain_agent/scripts/smoke_test.sh`

Lightweight curl-based testing without pytest dependencies. Suitable for CI/CD pipelines and quick validation.

**Features:**
- Color-coded output (pass/fail/info)
- Service connectivity checks
- Health endpoint validation
- Database and OpenSearch status
- API authentication tests
- Response time measurement
- HTTPS certificate validation
- Detailed error reporting

**Usage:**

```bash
# Local deployment
./scripts/smoke_test.sh http://localhost:8000

# Cloud Run deployment
./scripts/smoke_test.sh https://agentic-hybrid-search-xyz.us-central1.run.app

# Custom timeout and API key
API_KEY=my-api-key TIMEOUT=20 ./scripts/smoke_test.sh https://my-deployment

# Capture output
./scripts/smoke_test.sh http://localhost:8000 | tee smoke-test.log

# Check exit code
./scripts/smoke_test.sh http://localhost:8000
if [ $? -eq 0 ]; then echo "All tests passed"; fi
```

**Output Example:**

```
====== Agentic Hybrid Search - Deployment Smoke Tests ======

ℹ Testing deployment: http://localhost:8000

▬ Service Connectivity
✓ Service is accessible

▬ Health Checks
✓ Health endpoint responsive with all required fields
ℹ Response: {"status": "ok", "version": "1.1.0", ...}
✓ PostgreSQL is healthy
✓ OpenSearch is healthy
✓ Products indexed (count: 10000)

▬ Authentication
✓ Valid API key accepted (HTTP 200)
✓ Invalid API key properly rejected (HTTP 401)

▬ Performance
✓ Health check responded in 45ms

====== Test Summary ======
Total: 7 | Passed: 7 | Failed: 0

✓ All smoke tests passed!
```

## GitHub Actions Workflow

Location: `.github/workflows/deploy-smoke-test.yml`

Automated post-deployment testing triggered after successful Cloud Run deployment.

**Trigger:** Runs after `Build & Deploy` workflow completes successfully on `main` branch

**Steps:**
1. Checkout code
2. Set up Python 3.13
3. Install test dependencies
4. Get Cloud Run service URL from GCP
5. Wait for service to be ready (max 10 retries, 3-second intervals)
6. Run quick curl health check
7. Run pytest smoke test suite
8. Run Cloud Run deployment tests
9. Run data integrity tests
10. Upload test results as artifacts
11. Generate GitHub step summary with results

**Configuration:**
- **Timeout:** 15 minutes total
- **Service ready timeout:** 10 retries × 3 seconds = 30 seconds
- **Test markers:** `@pytest.mark.e2e @pytest.mark.slow`
- **Python version:** 3.13
- **pytest timeout:** 30 seconds per test

**Environment Variables:**
```bash
PROJECT_ID: gen-lang-client-0250737934
REGION: us-central1
SERVICE_NAME: agentic-hybrid-search
```

**Service Discovery:**
The workflow constructs the Cloud Run URL as:
```
https://{SERVICE_NAME}-375500751528.{REGION}.run.app
```

If this URL format changes, update the workflow's `Get Cloud Run service URL` step.

**Test Results:**
- Captured in GitHub artifacts for each workflow run
- Summary added to GitHub step summary
- Failed tests trigger notification step

## Running Tests Locally

### Prerequisites

```bash
cd langchain_agent

# Install test dependencies
pip install pytest pytest-asyncio httpx websockets

# Ensure local services running
docker compose up -d  # from repo root

# Start backend
python3 setup.py
make dev-api
```

### Against Localhost

```bash
# All smoke tests
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -v

# Specific test class
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestDeploymentHealth -v

# With increased verbosity
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -vv --tb=short

# Show print output
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -v -s
```

### Against Cloud Run

```bash
export CLOUD_RUN_URL="https://agentic-hybrid-search-xyz.us-central1.run.app"

# All tests
PYTHONPATH=. CLOUD_RUN_URL=$CLOUD_RUN_URL pytest tests/e2e/ -v

# Smoke tests only
PYTHONPATH=. CLOUD_RUN_URL=$CLOUD_RUN_URL pytest tests/e2e/test_deployment_smoke.py -v

# With custom timeout (30 seconds per test)
PYTHONPATH=. CLOUD_RUN_URL=$CLOUD_RUN_URL pytest tests/e2e/ -v --timeout=30
```

## Test Markers

Tests use pytest markers for selective execution:

```bash
# Run all E2E tests
PYTHONPATH=. pytest tests/e2e/ -m "e2e" -v

# Run slow tests (full suite)
PYTHONPATH=. pytest tests/e2e/ -m "slow" -v

# Run both E2E and slow
PYTHONPATH=. pytest tests/e2e/ -m "e2e and slow" -v

# Exclude slow tests
PYTHONPATH=. pytest tests/e2e/ -m "not slow" -v
```

## Environment Variables

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLOUD_RUN_URL` | `http://localhost:8000` | Deployment URL to test |
| `API_KEY` | `test-api-key` | API key for authenticated requests |
| `TIMEOUT` | `30` (pytest), `10` (curl) | Request timeout in seconds |
| `PYTHONPATH` | (not set) | Must be `.` for pytest to find modules |

### Examples

```bash
# Local with custom timeout
CLOUD_RUN_URL="http://localhost:8000" TIMEOUT=60 PYTHONPATH=. pytest tests/e2e/ -v

# Cloud Run with custom API key
CLOUD_RUN_URL="https://my-deployment.run.app" API_KEY="prod-key" PYTHONPATH=. pytest tests/e2e/ -v

# Bash script
API_KEY="my-key" TIMEOUT=20 ./scripts/smoke_test.sh https://my-deployment.run.app
```

## Troubleshooting

### Tests Fail with "Connection refused"

**Issue:** Service not running or URL incorrect

**Solutions:**
```bash
# Verify service is running
curl http://localhost:8000/api/health

# Check Cloud Run URL format
# Should be: https://SERVICE_NAME-HASH.REGION.run.app
gcloud run services describe agentic-hybrid-search --region=us-central1
```

### Tests Timeout

**Issue:** Service taking too long to respond

**Solutions:**
```bash
# Increase timeout
TIMEOUT=60 PYTHONPATH=. pytest tests/e2e/ -v

# Check service logs
gcloud run services logs read agentic-hybrid-search --region=us-central1

# Check service resources
gcloud run services describe agentic-hybrid-search --region=us-central1
```

### WebSocket Tests Fail

**Issue:** WebSocket connection refused or timeout

**Solutions:**
```bash
# Verify WebSocket endpoint is accessible
curl -i http://localhost:8000/api/health

# Check firewall rules on Cloud Run
gcloud run services describe agentic-hybrid-search --format="value(status.ingress)"

# Verify CORS configuration in config.py
grep CORS_ORIGINS langchain_agent/config.py
```

### Authentication Tests Fail

**Issue:** API key validation failing

**Solutions:**
```bash
# Check API key is set
echo $API_KEY

# Verify key in environment
env | grep API_KEY

# Check middleware logs
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestAuthentication -v -s
```

### Data Tests Fail

**Issue:** Products not found or indices not initialized

**Solutions:**
```bash
# Check product ingestion
curl http://localhost:8000/api/health | grep document_count

# Verify OpenSearch index
curl http://localhost:9200/_cat/indices

# Re-index products
cd langchain_agent
PYTHONPATH=. python ingest_esci_products.py
```

## Performance Expectations

### Latency Targets

- **Health check:** < 100ms
- **Search intent:** < 5 seconds (excluding network)
- **Generation:** < 10 seconds (excluding network)
- **WebSocket connection:** < 1 second

### Throughput

- **Concurrent connections:** 5+ simultaneous
- **Burst load:** 20 requests handled with > 70% success rate
- **Concurrent searches:** No errors under 10 parallel requests

## CI/CD Integration

### GitHub Actions

The `deploy-smoke-test.yml` workflow is automatically triggered after successful deployment.

**Configuration in GitHub:**
1. Create workflow file (already done): `.github/workflows/deploy-smoke-test.yml`
2. No additional setup required
3. Results appear in:
   - Workflow run logs
   - GitHub artifacts (test results)
   - GitHub step summary

### Manual Trigger

```bash
# Trigger workflow via GitHub CLI
gh workflow run deploy-smoke-test.yml --ref main

# View workflow status
gh run list --workflow=deploy-smoke-test.yml --limit 5

# View latest results
gh run view $(gh run list --workflow=deploy-smoke-test.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

### Pre-deployment Validation

Run tests before pushing to main:

```bash
# Local validation
./scripts/smoke_test.sh http://localhost:8000

# Or with pytest
make dev-api &  # Start backend
PYTHONPATH=. pytest tests/e2e/ -v -m "e2e and slow"
kill %1  # Stop backend
```

## Best Practices

1. **Run locally first** — Test against localhost before Cloud Run
2. **Use markers** — Run by `@pytest.mark.e2e` to exclude unit tests
3. **Check artifacts** — Download smoke test results after Cloud Run deployment
4. **Monitor latency** — Watch for performance regressions
5. **Validate data** — Run `test_deployment_data.py` after ingestion
6. **Test authentication** — Verify API keys work in production
7. **Monitor scaling** — Verify concurrent request handling
8. **Review logs** — Check Cloud Logging for errors during smoke tests

## Related Documentation

- [Deployment Checklist](../../DEPLOYMENT_CHECKLIST.md) — Pre-deployment validation
- [GCP Cloud Run Setup](../../scripts/gcp-init.sh) — Cloud Run initialization
- [CLAUDE.md](../../CLAUDE.md) — Project architecture and testing patterns
- [GitHub Actions Workflow](../../.github/workflows/build-deploy.yml) — CI/CD pipeline
