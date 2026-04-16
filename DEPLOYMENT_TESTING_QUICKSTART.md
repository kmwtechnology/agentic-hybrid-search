# Deployment Testing - Quick Start Guide

Comprehensive deployment validation suite with 45+ tests covering health checks, authentication, scaling, and data integrity.

## What Was Added

### Test Files (45 tests total)
- **`test_deployment_smoke.py`** — 17 core smoke tests (health, auth, WebSocket, search, timing)
- **`test_cloud_run_deployment.py`** — 18 Cloud Run-specific tests (HTTPS, scaling, graceful shutdown)
- **`test_deployment_data.py`** — 10 data integrity tests (product indexing, consistency, checkpoints)

### Scripts & Workflows
- **`scripts/smoke_test.sh`** — Standalone bash validation (no pytest required)
- **`.github/workflows/deploy-smoke-test.yml`** — Automated post-deployment testing
- **`tests/e2e/DEPLOYMENT_TESTING.md`** — Comprehensive testing documentation

## Quick Test Commands

### Against Localhost (After Starting Backend)

```bash
# Start services
docker compose up -d
cd langchain_agent
python3 setup.py
make dev-api  # in background or separate terminal

# Run all tests
PYTHONPATH=. pytest tests/e2e/ -v -m "e2e and slow"

# Or use bash script (no pytest needed)
./scripts/smoke_test.sh http://localhost:8000
```

### Against Cloud Run Deployment

```bash
# Set deployment URL
export CLOUD_RUN_URL="https://agentic-hybrid-search-xyz.us-central1.run.app"

# Run all tests
PYTHONPATH=. pytest tests/e2e/ -v -m "e2e and slow"

# Or use bash script
./scripts/smoke_test.sh $CLOUD_RUN_URL
```

## Test Coverage

### Health & Connectivity (7 tests)
- Health endpoint returns correct status and version
- PostgreSQL connectivity
- Google AI API availability
- OpenSearch index status
- Product document count (> 0)

### Authentication (3 tests)
- Valid API key accepted
- Invalid API key rejected
- Missing API key rejected

### WebSocket (3 tests)
- Connection establishment
- Message reception and processing
- Streaming response handling

### Search Functionality (3 tests)
- Search intent returns results
- Comparison intent
- Refinement intent with context

### Cloud Run Specific (8 tests)
- HTTPS certificate validation
- Concurrent connections (5+ simultaneous)
- Burst load handling (20 requests)
- Graceful shutdown behavior
- Secret Manager integration
- JSON logging format

### Data Integrity (10 tests)
- ESCI products indexed
- Hybrid search (vector + lexical)
- Vector search semantic similarity
- Lexical search exact matches
- Product metadata completeness
- Brand attribute indexing
- Result consistency
- Checkpoint persistence
- Data corruption detection

### Performance (2 tests)
- Search latency < 5 seconds (+ network)
- Generation latency < 10 seconds (+ network)

## Running Specific Tests

```bash
# Just health checks
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestDeploymentHealth -v

# Just authentication
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestAuthentication -v

# Just WebSocket tests
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestWebSocketConnectivity -v

# Just Cloud Run scaling tests
PYTHONPATH=. pytest tests/e2e/test_cloud_run_deployment.py::TestHorizontalScaling -v

# Just data tests
PYTHONPATH=. pytest tests/e2e/test_deployment_data.py::TestESCIProductIndexing -v

# Search intent only
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestSearchPipeline::test_search_intent_returns_results -v
```

## Bash Script Usage

No pytest required. Lightweight curl-based validation:

```bash
# Basic usage
./scripts/smoke_test.sh http://localhost:8000

# Cloud Run
./scripts/smoke_test.sh https://agentic-hybrid-search-xyz.us-central1.run.app

# With custom API key
API_KEY=my-api-key ./scripts/smoke_test.sh https://my-deployment

# Custom timeout
TIMEOUT=60 ./scripts/smoke_test.sh http://localhost:8000

# Capture results
./scripts/smoke_test.sh http://localhost:8000 | tee smoke-test.log

# Check exit code
./scripts/smoke_test.sh http://localhost:8000
echo "Exit code: $?"
```

## GitHub Actions Integration

Automatically runs after Cloud Run deployment on `main` branch.

**Triggered by:** Build & Deploy workflow completion
**When:** After successful Docker build and Cloud Run deployment
**What:** Runs all 45 smoke tests against deployed service
**Results:** Artifacts + GitHub step summary

View results:
1. Go to GitHub Actions tab
2. Find "Post-Deployment Smoke Tests" workflow run
3. Check "smoke-test-results" artifact
4. Review step summary at end of workflow

## Test Environment Variables

```bash
# All tests respect these variables
CLOUD_RUN_URL=http://localhost:8000       # Deployment URL (default: localhost)
API_KEY=test-api-key                       # API key for auth tests
TIMEOUT=30                                  # Request timeout in seconds
PYTHONPATH=.                                # Required for pytest
```

## Expected Output

### Pytest (Verbose)

```
tests/e2e/test_deployment_smoke.py::TestDeploymentHealth::test_health_endpoint_returns_ok PASSED
tests/e2e/test_deployment_smoke.py::TestDeploymentHealth::test_health_checks_postgres PASSED
tests/e2e/test_deployment_smoke.py::TestAuthentication::test_valid_api_key_accepted PASSED
...
========================= 45 passed in 58.32s =========================
```

### Bash Script

```
▶ Testing health endpoint
✓ Health endpoint responsive with all required fields
✓ PostgreSQL is healthy
✓ OpenSearch is healthy
✓ Products indexed (count: 10000)

✓ Valid API key accepted (HTTP 200)
✓ Invalid API key properly rejected (HTTP 401)

====== Test Summary ======
Total: 7 | Passed: 7 | Failed: 0

✓ All smoke tests passed!
```

## Troubleshooting

### "Connection refused"

Service not running:

```bash
# Verify service URL
curl http://localhost:8000/api/health

# Check backend logs
tail -f /tmp/agentic*.log
```

### Tests timeout

Increase timeout:

```bash
TIMEOUT=60 PYTHONPATH=. pytest tests/e2e/ -v
```

### WebSocket fails

Check CORS and auth:

```bash
# Check CORS origins in config
grep CORS_ORIGINS langchain_agent/config.py

# Check auth middleware
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestWebSocketConnectivity -v -s
```

### No products found

Re-ingest data:

```bash
cd langchain_agent
docker compose up -d
PYTHONPATH=. python ingest_esci_products.py --limit 1000
```

## File Locations

```
langchain_agent/
├── tests/e2e/
│   ├── test_deployment_smoke.py          # Core smoke tests (17 tests)
│   ├── test_cloud_run_deployment.py      # Cloud Run tests (18 tests)
│   ├── test_deployment_data.py           # Data integrity tests (10 tests)
│   └── DEPLOYMENT_TESTING.md             # Full documentation
├── scripts/
│   └── smoke_test.sh                      # Standalone bash script
└── .github/workflows/
    └── deploy-smoke-test.yml             # GitHub Actions automation
```

## Next Steps

1. **Test Locally** — Run against localhost with `./scripts/smoke_test.sh http://localhost:8000`
2. **Deploy** — Push to main branch, GitHub Actions automatically runs tests
3. **Monitor** — Check GitHub Actions tab for test results
4. **Iterate** — Update tests based on your deployment needs

## Full Documentation

See `langchain_agent/tests/e2e/DEPLOYMENT_TESTING.md` for:
- Detailed test descriptions
- Configuration options
- Performance expectations
- CI/CD integration
- Best practices
- Troubleshooting guide
