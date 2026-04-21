# End-to-End Tests

E2E tests exercise a **deployed Cloud Run instance** end to end — health,
auth, WebSocket streaming, pipeline correctness across all 6 intents,
ESCI data presence, latency profile, and behavior under load.

These are pytest + httpx + websockets tests (not browser automation).
See [`DEPLOYMENT_TESTING.md`](DEPLOYMENT_TESTING.md) for the full testing
workflow.

## Prerequisites

```bash
export CLOUD_RUN_URL="https://agentic-hybrid-search-xyz.us-central1.run.app"
export API_KEY="..."                # must match Secret Manager
PYTHONPATH=. pytest tests/e2e/ -v
```

All suites auto-skip individual tests when the target origin rejects the
request (via `_skip_if_origin_blocked`) — useful when CORS or VPC rules
block certain paths from your workstation but you still want the rest of
the suite to run.

## Test Files

### `test_deployment_smoke.py` — basic contract

- `TestDeploymentHealth` — `/api/health` returns 200 + expected fields
- `TestAuthentication` — missing/invalid key → 401, valid key → 200, constant-time compare
- `TestWebSocketConnectivity` — `/api/chat` upgrade, origin checks, auth via header/query
- `TestSearchPipeline` — each of the 6 intents (`search`, `comparison`, `attribute_filter`, `refinement`, `follow_up`, `summary`) produces a valid response with expected event ordering
- `TestCitations` — citation URLs present when reranker score ≥ 0.10, Amazon `dp/{ASIN}` shape
- `TestResponseTiming` — end-to-end latency budget assertions

### `test_cloud_run_deployment.py` — infrastructure behavior

- `TestCloudRunConnectivity` — DNS, TLS, HTTP/2
- `TestRequestTimeout` — long-running requests don't exceed Cloud Run's request timeout
- `TestGracefulShutdown` — in-flight requests finish on revision cutover
- `TestHorizontalScaling` — traffic burst spawns replicas without error spikes
- `TestLoggingFormat` — structured logs parse as JSON
- `TestEnvironmentConfiguration` — expected env/config surfaced via `/api/health`
- `TestDatabaseConnectivity` — Cloud SQL reachable through the proxy
- `TestOpenSearchIndex` — hosted OpenSearch reachable, index non-empty

### `test_deployment_data.py` — data layer

- `TestESCIProductIndexing` — product docs present with the expected dual-mapped fields
- `TestProductMetadata` — `product_brand.keyword`, `product_color.keyword`, `product_locale`
- `TestDataConsistency` — facet counts, sample product round-trip
- `TestCheckpointPersistence` — conversation state survives across requests

### `test_real_world_scenarios.py` — user journeys

Seven scenario classes covering realistic personas end-to-end:

- `TestEcommerceShopperScenario` — search → compare → refine → follow-up
- `TestProductExpertScenario` — deep attribute-filter queries, technical language
- `TestContentCreatorScenario` — Product Comparison Writer across all 5 content types
- `TestSupportAgentScenario` — summary intent, conversation history
- `TestMobileShopperScenario` — short queries, high follow-up rate
- `TestAccessibilityScenario` — screen-reader-friendly output, alt text in citations
- `TestPowerUserScenario` — rapid multi-turn conversations

Plus `TestColdStartPerformance` and `TestStreamingNetworkConditions` for
first-request latency and flaky-network behavior.

### `test_latency_profiling.py` — per-stage latency

- `TestStageLatencies` — budgets per node (classifier, evaluator, retriever, reranker, quality gate, agent)
- `TestAlphaComparison` — fast-path α vs LLM-path α latency delta
- `TestFullPipelineProfile` — end-to-end breakdown summed from observability events
- `TestMemoryProfileing` — RSS growth under repeated requests
- `TestCacheEffectiveness` — embedding cache hit rate after warm-up

### `test_performance_load.py` — throughput

- `TestLoadPerformance` — sustained RPS, p50/p95/p99
- `TestSearchLatencyProfiles` — per-intent latency distributions
- `TestRerankerPerformance` — reranker time as a function of candidate count
- `TestMemoryUsage` — heap growth under load
- `TestRegressionDetection` — compares against a checked-in baseline

Exports JSON (`performance_report.json`) for trend tracking.

### `test_stress.py` — failure modes under pressure

- `TestSustainedLoad` — long-duration sustained traffic
- `TestBurstLoad` — spike traffic handling
- `TestConnectionPooling` — WebSocket pool behavior
- `TestErrorRecovery` — recovery from transient upstream errors (OpenSearch, Gemini 429s)
- `TestResourceLeakDetection` — file descriptors, memory, connections over time

Exports `stress_report.json`.

## Intent Coverage Matrix

Each intent is exercised by at least one smoke test and one scenario test:

| Intent | Smoke | Scenario |
|--------|-------|----------|
| `search` | `TestSearchPipeline::test_search_intent` | `TestEcommerceShopperScenario` |
| `comparison` | `TestSearchPipeline::test_comparison_intent` | `TestProductExpertScenario` |
| `attribute_filter` | `TestSearchPipeline::test_attribute_filter_intent` | `TestEcommerceShopperScenario` |
| `refinement` | `TestSearchPipeline::test_refinement_intent` | `TestEcommerceShopperScenario` |
| `follow_up` | `TestSearchPipeline::test_follow_up_intent` | `TestMobileShopperScenario` |
| `summary` | `TestSearchPipeline::test_summary_intent` | `TestSupportAgentScenario` |

## Quality Gate Coverage

Dedicated assertions for the `< 0.5` retry behavior live in
[`../integration/test_quality_gate_retry.py`](../integration/test_quality_gate_retry.py).
The E2E suite confirms the gate's event shape (`QualityGateEvent` with
`decision`, `max_score`, `alpha_adjusted_value`) reaches the frontend
via WebSocket.

## Success Criteria

The suite guards against regressions in:

- **Correctness** — every intent routes to the right node set and produces a response
- **Latency** — per-node budgets hold against the checked-in baselines
- **Reliability** — ≥ 99% success rate at sustained target RPS
- **Data integrity** — ESCI index population, checkpoint durability
- **Streaming contract** — token events arrive in order, `AgentCompleteEvent` terminates the stream

## Running Selectively

```bash
# Just smoke
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py -v

# All intents, no load
PYTHONPATH=. pytest tests/e2e/test_deployment_smoke.py::TestSearchPipeline -v

# Load/stress only
PYTHONPATH=. pytest tests/e2e/ -m "load or stress" -v

# Skip slow scenarios
PYTHONPATH=. pytest tests/e2e/ -m "not slow" -v
```

## Reports

Load and stress runs emit JSON:

- `performance_report.json` — `test_performance_load.py`
- `stress_report.json` — `test_stress.py`

Commit baselines you care about next to the suite so
`TestRegressionDetection` can compare future runs against them.

## See Also

- [`DEPLOYMENT_TESTING.md`](DEPLOYMENT_TESTING.md) — full testing
  workflow from deploy to sign-off
- [`../PERFORMANCE_TESTING.md`](../PERFORMANCE_TESTING.md) — perf-testing
  methodology shared across integration and e2e
- [`../README.md`](../README.md) — overall test suite layout
