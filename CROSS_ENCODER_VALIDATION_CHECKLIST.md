# Cross-Encoder Reranker Validation Checklist

## Risk Assessment: Major Component Change
Switching from Gemini LLM reranker to local cross-encoder affects:
- **Score distribution** → citation filtering (min threshold 0.10)
- **Quality gate logic** → may trigger differently with new scores
- **Observable events** → reranker timing/metrics may change
- **Error handling** → new failure modes (model loading, CUDA issues)
- **Latency profile** → cold-start penalties on Cloud Run

---

## Pre-Deployment Validation

### 1. **Score Distribution Test** 🎯
- [ ] Verify sigmoid normalization produces usable scores
- [ ] Confirm adaptive rescaling doesn't mask real low-score docs
- [ ] Check score mean/median comparable to Gemini baseline
- [ ] Validate top-k ranking order preserved after rescaling

**Test Method**: Add score logging (DONE in 44d7978), run local searches, inspect logs:
```
cross_encoder_scores: raw_logits={min: X, max: Y, mean: Z}
                      normalized={min: A, max: B, mean: C}
                      below_citation_threshold_0.10: N
```

### 2. **Citations Pipeline** 🔍 (Issue #17 Fix Verification)
- [ ] Ensure citations NOT empty with cross-encoder scores
- [ ] Verify min_relevance_threshold (0.10) doesn't filter all docs
- [ ] Check agent_node returns citations in ALL code paths
- [ ] Validate citations dedup and URL generation work correctly

**Test Method**: Local smoke test with debug logging:
```bash
PYTHONPATH=. pytest tests/e2e/test_smoke.py::test_products_have_required_metadata -v
# Should show: citations > 0 for typical "headphones" query
```

### 3. **Quality Gate Logic** ⚙️
- [ ] Quality gate threshold detection works with new score distribution
- [ ] Retry mechanism triggers appropriately (if max_score too low)
- [ ] Alpha adjustment strategy still makes sense with new scores
- [ ] No infinite loops from quality gate retries

**Potential Issue**: If cross-encoder always produces max_score 0.4-0.6, quality gate may trigger retries differently than Gemini (which often produces 0.7+).

### 4. **Observable Agent Events** 📡
- [ ] RerankerStartEvent emitted correctly
- [ ] RerankerProgressEvent has correct stage/progress
- [ ] PipelineSummaryEvent reranker metrics make sense
- [ ] No missing node fields in event stream

**Check**: Run with observability panel, verify events stream correctly in UI.

### 5. **Error Handling & Edge Cases** ⚠️
- [ ] Model download on first cold-start (Cloud Run)
- [ ] Fallback if sentence-transformers import fails
- [ ] Handle empty document list gracefully
- [ ] Handle very large document batches (>100 docs)

**Potential Issues**:
- Cloud Run cold-start: model downloaded = 200MB + setup time
- Out-of-memory: if batch_size (32) too large for available RAM
- Timeout: if warmup takes >30s, could delay startup

### 6. **Fallback & Rollback Path** 🔄
- [ ] Verify `RERANKER_TYPE=gemini` still works (GeminiReranker untouched)
- [ ] Config default is cross-encoder (not gemini)
- [ ] Easy rollback: just change env var, no code changes

**Rollback Test**: 
```bash
RERANKER_TYPE=gemini python3 main.py  # Should load Gemini reranker
```

### 7. **Performance Validation** ⚡
- [ ] Reranker latency < 50ms (vs 500ms Gemini)
- [ ] Total E2E latency improved by 400ms+ on avg query
- [ ] Cold-start time acceptable (model load + warmup)
- [ ] No memory leaks (monitor on Cloud Run for 24h)

**Metrics to Verify**:
- `reranker_latency_ms` in logs (should be 10-50ms)
- Total user query latency vs Gemini baseline
- Cloud Run memory usage over time

### 8. **Integration Test Coverage** 🧪
- [ ] All reranker unit tests pass (8 mocked CrossEncoderReranker tests)
- [ ] No new import errors or dependency conflicts
- [ ] Integration tests collect-only passes (no runtime failures)
- [ ] E2E smoke tests pass on Cloud Run

**Run Before Deploy**:
```bash
PYTHONPATH=. pytest tests/unit/test_reranker.py -v
make ci  # black + isort + flake8 + mypy + collect-only
```

---

## Post-Deployment Monitoring (Cloud Run)

### First 24 Hours
- [ ] Monitor `/health` endpoint responds in <500ms
- [ ] Cloud Run logs for `cross_encoder_error` (reranker failures)
- [ ] Cloud Run logs for score distribution anomalies
- [ ] User reports of missing citations (monitoring dashboard)

### 1-Week Review
- [ ] Latency improvement confirmed vs Gemini
- [ ] No increase in error rates
- [ ] Citations present in typical queries
- [ ] Quality gate retries at expected frequency
- [ ] Memory/CPU metrics stable

### Rollback Criteria (If Issues Found)
```bash
# Immediate rollback if any of:
- Citations missing in >5% of queries
- Reranker errors in >1% of requests
- Latency increase vs Gemini
- Cold-start >60s
- Memory OOM errors
```

**Rollback**: Set `RERANKER_TYPE=gemini` in Secret Manager, restart Cloud Run.

---

## Summary of Safety Changes

✅ **Commit 4847ecc**: CrossEncoderReranker class + factory pattern  
✅ **Commit f26d0c3**: Fixed unit test mocking  
✅ **Commit 44d7978**: Added score calibration + diagnostics  

**Next Step**: Run full validation suite, monitor cloud metrics, greenlight for production.
