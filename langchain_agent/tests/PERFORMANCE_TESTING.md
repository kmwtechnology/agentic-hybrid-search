# Performance Testing Guide for Agentic Hybrid Search

Comprehensive performance testing suite covering load testing, stress testing, latency profiling, and real-world scenario validation.

## Overview

The performance testing suite consists of four main test modules:

### 1. Load Testing (`tests/e2e/test_performance_load.py`)
Tests system behavior under concurrent load with increasing user counts.

**Scenarios:**
- Single user baseline (1 user, 5 queries)
- Light load (5 concurrent users, 3 queries each)
- Medium load (10 concurrent users, 2 queries each)
- Heavy load (20 concurrent users, 1 query each)

**Measurements:**
- Latency: p50, p95, p99 percentiles (milliseconds)
- Throughput: Requests per second
- Error rates
- Token consumption
- Memory usage over time

**Test Classes:**
- `TestLoadPerformance` — Concurrent user load tests
- `TestSearchLatencyProfiles` — Search latency across alpha values
- `TestRerankerPerformance` — Reranker timing and accuracy
- `TestMemoryUsage` — Memory leak detection
- `TestRegressionDetection` — Baseline comparison

### 2. Real-World Scenarios (`tests/e2e/test_real_world_scenarios.py`)
Tests realistic user journeys and interaction patterns.

**Scenarios:**
1. **E-commerce Shopper** — Browse → Filter → Compare → Decision (5-turn conversation)
2. **Product Expert** — Deep technical specifications and compatibility (4-turn)
3. **Content Creator** — Multi-format content generation (social, blog, article)
4. **Support Agent** — Customer support with citations (4-turn)
5. **Mobile Shopper** — Rapid-fire queries with tight latency budget
6. **Power User** — Complex filtering, faceting, refinements
7. **Accessibility User** — Screen reader compatible responses
8. **Cold Start** — First request after deployment (warm-up)
9. **Streaming Network** — WebSocket behavior under jitter

**Test Classes:**
- `TestEcommerceShopperScenario`
- `TestProductExpertScenario`
- `TestContentCreatorScenario`
- `TestSupportAgentScenario`
- `TestMobileShopperScenario`
- `TestAccessibilityScenario`
- `TestPowerUserScenario`
- `TestColdStartPerformance`
- `TestStreamingNetworkConditions`

### 3. Stress Testing (`tests/e2e/test_stress.py`)
Tests system behavior under extreme conditions and failure scenarios.

**Scenarios:**
- Sustained load: 50 concurrent users for 1 minute
- Burst load: 100 requests in 10 seconds
- Connection pool exhaustion: 50 concurrent connections
- Error recovery: Timeout and reconnection behavior
- Malformed requests: Invalid input handling

**Test Classes:**
- `TestSustainedLoad` — Long-duration high concurrency
- `TestBurstLoad` — Short spike testing
- `TestConnectionPooling` — Connection pool behavior
- `TestErrorRecovery` — Recovery from failures
- `TestResourceLeakDetection` — Memory leak detection

### 4. Latency Profiling (`tests/e2e/test_latency_profiling.py`)
Profiles each pipeline stage to identify bottlenecks.

**Stages:**
1. Query embedding generation
2. Vector search (hybrid search with different alphas)
3. Document reranking
4. Token generation
5. Full pipeline execution

**Test Classes:**
- `TestStageLatencies` — Individual stage timing
- `TestAlphaComparison` — Lexical vs semantic search latency
- `TestFullPipelineProfile` — Complete pipeline profiling
- `TestMemoryProfileing` — Memory allocation by stage
- `TestCacheEffectiveness` — Cache hit benefits

## Running Tests

### Run All Performance Tests
```bash
cd langchain_agent
PYTHONPATH=. pytest tests/e2e/test_performance_load.py tests/e2e/test_real_world_scenarios.py tests/e2e/test_stress.py tests/e2e/test_latency_profiling.py -v --tb=short -m performance
```

### Run by Category
```bash
# Load tests only
PYTHONPATH=. pytest -m load -v

# Stress tests only
PYTHONPATH=. pytest -m stress -v

# Profiling tests only
PYTHONPATH=. pytest -m profile -v

# Scenario tests only (no marker, run specific file)
PYTHONPATH=. pytest tests/e2e/test_real_world_scenarios.py -v
```

### Run Specific Test Class
```bash
# Single scenario
PYTHONPATH=. pytest tests/e2e/test_real_world_scenarios.py::TestEcommerceShopperScenario -v

# Load with 10 users
PYTHONPATH=. pytest tests/e2e/test_performance_load.py::TestLoadPerformance::test_10_concurrent_users -v

# Stress with 50 users
PYTHONPATH=. pytest tests/e2e/test_stress.py::TestSustainedLoad::test_sustained_50_users_60_seconds -v
```

### Run With Benchmark Harness
```bash
# Run all benchmarks
python -m benchmark.benchmark_harness --all

# Run specific category
python -m benchmark.benchmark_harness --load
python -m benchmark.benchmark_harness --stress
python -m benchmark.benchmark_harness --profile

# Compare against baseline
python -m benchmark.benchmark_harness --compare-baseline

# Generate HTML report
python -m benchmark.benchmark_harness --report

# Save current run as baseline
python -m benchmark.benchmark_harness --all --save-baseline
```

## Metrics and Thresholds

### Load Testing Thresholds
| Metric | Threshold | Notes |
|--------|-----------|-------|
| p50 latency (single user) | < 5 seconds | Baseline target |
| p95 latency (single user) | < 10 seconds | Acceptable variance |
| Error rate (1 user) | < 10% | Should be near zero |
| Error rate (5 users) | < 15% | Slight degradation OK |
| Error rate (10 users) | < 20% | Further degradation |
| Error rate (20 users) | < 25% | Limit of graceful degradation |
| Memory growth | < 50MB per burst | Detect memory leaks |

### Stress Testing Thresholds
| Metric | Threshold | Notes |
|--------|-----------|-------|
| Sustained (50 users/60s) success rate | > 70% | System remains functional |
| Burst (100 requests/10s) success rate | > 60% | Handling spike load |
| Timeout errors (burst) | < 15% | Timeouts acceptable under extreme load |
| Connection errors | < 20% | Pool exhaustion possible |
| p99 latency (burst) | < 30 seconds | Some requests can be slow |
| Memory leak | None detected | Should be stable over time |

### Latency Profiling Thresholds
| Stage | Threshold | Notes |
|-------|-----------|-------|
| Embedding generation | < 2 seconds (avg) | Fast query encoding |
| Vector search | < 3 seconds (avg) | Index performance |
| Reranking (10 docs) | < 5 seconds (avg) | LLM overhead |
| Full pipeline | < 15 seconds (avg) | End-to-end |
| Lexical (alpha=0.0) | < semantic latency | BM25 should be faster |

### Scenario Testing Expectations
| Scenario | Turns | Latency Budget | Success Rate |
|----------|-------|-----------------|--------------|
| E-commerce Shopper | 5 | 5s avg/turn | 100% |
| Product Expert | 4 | 5s avg/turn | 100% |
| Content Creator | 4 | 20s avg/turn | 100% |
| Support Agent | 4 | 3s avg/turn | 100% |
| Mobile Shopper | 5 | 2s avg/turn | 100% |
| Power User | 4 | 5s avg/turn | 100% |
| Accessibility | 1 | 5s | 100% |
| Cold Start | 1 | 30s (warm-up) | 100% |

## Performance Results

Results are stored in `tests/performance_results/`:

```
tests/performance_results/
├── baseline.json                    # Current baseline metrics
├── run_<timestamp>.json             # Individual run results
├── performance_results/
│   ├── baseline.json
│   ├── run_<timestamp>.json
│   └── performance_report_<timestamp>.json
├── stress_results/
│   ├── sustained_50_users.json
│   ├── burst_100_requests.json
│   └── stress_report_<timestamp>.json
└── profiling_results/
    ├── full_pipeline_profiles.json
    ├── alpha_comparison.json
    ├── bottleneck_analysis.json
    ├── memory_allocation.json
    ├── cache_effectiveness.json
    └── latency_report_<timestamp>.json
```

## Regression Detection

Performance regressions are detected by comparing against baseline:

```bash
# Compare current performance to baseline
python -m benchmark.benchmark_harness --compare-baseline
```

**Regression thresholds:**
- > 10% latency increase: REGRESSION
- 5-10% latency increase: WARNING
- < 5% latency increase: OK

If regression detected, the script returns exit code 1 for CI/CD integration.

## Integration with CI/CD

### GitHub Actions Workflow Example
```yaml
name: Performance Tests

on: [push, pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install -r langchain_agent/requirements.txt
      
      - name: Start services
        run: |
          docker compose up -d
      
      - name: Run performance tests
        run: |
          cd langchain_agent
          PYTHONPATH=. python -m benchmark.benchmark_harness --all
      
      - name: Check for regressions
        run: |
          cd langchain_agent
          PYTHONPATH=. python -m benchmark.benchmark_harness --compare-baseline
      
      - name: Generate report
        if: always()
        run: |
          cd langchain_agent
          PYTHONPATH=. python -m benchmark.benchmark_harness --report
      
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: performance-results
          path: langchain_agent/tests/performance_results/
```

## Best Practices

### Running Tests Locally
1. **Ensure services are running:**
   ```bash
   docker compose up -d  # Start PostgreSQL + OpenSearch
   ```

2. **Start with baseline:**
   ```bash
   python -m benchmark.benchmark_harness --all --save-baseline
   ```

3. **Make changes and test:**
   ```bash
   # Code changes...
   python -m benchmark.benchmark_harness --all --compare-baseline
   ```

4. **Review results:**
   ```bash
   python -m benchmark.benchmark_harness --report
   # Open tests/performance_results/report_*.html
   ```

### Interpreting Results

**Normal variance:** 5-10% latency variance between runs is normal due to:
- System load variations
- Garbage collection timing
- Network jitter
- LLM response variability

**Real regressions:** Look for:
- Consistent > 10% slowdown across multiple runs
- Increased error rates
- Memory growth over time
- Specific stage becoming significantly slower

### Optimization Workflow

1. **Run profiling** to identify bottleneck:
   ```bash
   PYTHONPATH=. pytest -m profile -v
   ```

2. **Check bottleneck analysis:**
   ```bash
   cat tests/profiling_results/bottleneck_analysis.json
   ```

3. **Implement optimization**

4. **Run load test** to verify improvement:
   ```bash
   PYTHONPATH=. pytest tests/e2e/test_performance_load.py::TestLoadPerformance::test_single_user_baseline -v
   ```

5. **Save new baseline** if improvement is real:
   ```bash
   python -m benchmark.benchmark_harness --all --save-baseline
   ```

## Troubleshooting

### Tests timeout (30s default)
- Increase timeout in test file if needed for cold starts
- Ensure services are healthy: `curl http://localhost:8000/api/health`

### High error rates
- Check service logs: `docker compose logs opensearch` or `docker compose logs postgres`
- Verify API key is set: `echo $API_KEY`
- Check network connectivity

### Memory leak suspected
- Run memory profiling test: `PYTHONPATH=. pytest tests/e2e/test_performance_load.py::TestMemoryUsage -v`
- Check for circular references in agent code
- Verify connection pools are being closed properly

### Inconsistent results
- Close background applications (browsers, IDEs, etc.)
- Run multiple times to establish variance baseline
- Use same hardware for consistent comparisons

## References

- [Load Testing Best Practices](https://en.wikipedia.org/wiki/Load_testing)
- [Stress Testing Methodology](https://en.wikipedia.org/wiki/Stress_testing)
- [Latency Profiling Techniques](https://en.wikipedia.org/wiki/Profiling_(computer_programming))
- [pytest Documentation](https://docs.pytest.org/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
