# Post-Deployment Validation Checklist - Run #159

## Immediate (Once Deployment Completes)

### Test Results Verification
- [ ] **Run #159 overall status**: Check if conclusion is "success"
- [ ] **Unit tests**: 696/696 passed
- [ ] **Integration tests**: All passed (PostgreSQL + OpenSearch)
- [ ] **Frontend tests**: 118/118 passed
- [ ] **Smoke tests**: 20/20 passed
  - [ ] Health checks
  - [ ] Authentication tests
  - [ ] WebSocket connectivity
  - [ ] Search intent tests
  - [ ] Citations validation
  - [ ] Response timing (<5s and <10s)
- [ ] **Cloud Run tests**: 17/17 passed
- [ ] **Data tests**: 10/10 passed
  - [ ] ✅ `test_product_brand_attribute_accessible` — **CRITICAL**: Should now PASS

### If All Tests Pass ✅
1. Update task #2 to completed
2. Cross-encoder reranker deployment successful
3. Both env var fix and event emission fix validated

### If Data Test Still Fails ⚠️
1. Review Cloud Run logs for "Apple brand" queries
2. Check if LLM is returning actual empty content or if there's another issue
3. Consider if test needs adjustment (e.g., query too specific for index)
4. May need fallback response for empty LLM outputs

## Short Term (First 24 Hours Post-Deployment)

### Cloud Run Service Health
```bash
# Check health endpoint
curl https://agentic-hybrid-search-375500751528.us-central1.run.app/api/health

# Expected response
{
  "status": "ok",
  "version": "1.1.0",
  "postgres": true,
  "google_ai": true,
  "vector_store": true,
  "document_count": 9618
}
```

### Log Monitoring
- Monitor `/health` endpoint latency (target: <500ms)
- Check Cloud Run logs for errors related to:
  - Cross-encoder model initialization
  - Reranker scoring failures
  - Empty LLM responses
  - Event emission issues

```bash
# Monitor logs in real-time
gcloud run services logs read agentic-hybrid-search \
  --region=us-central1 \
  --project=gen-lang-client-0250737934 \
  --limit=100 \
  --format="json" | jq -r '.[] | "\(.timestamp) [\(.severity)] \(.textPayload)"'
```

### Key Metrics to Check
- **Reranker latency**: Should be 10-50ms (vs 500ms for Gemini)
- **Total query latency**: Should show ~450ms improvement
- **Error rate**: Should be <1% in reranker
- **Empty response rate**: Monitor for silent failures

## Integration Validation (If Concerns Arise)

### Test Specific Scenarios
```bash
# From within langchain_agent/ directory:

# Test brand search locally (if environment mirrors Cloud Run)
CLOUD_RUN_URL=https://agentic-hybrid-search-375500751528.us-central1.run.app \
LOGIN_PASSWORD=$(grep '^LOGIN_PASSWORD=' ../.env | cut -d= -f2) \
PYTHONPATH=. python -m pytest \
  tests/e2e/test_deployment_data.py::TestProductMetadata::test_product_brand_attribute_accessible \
  -v -ra --tb=short --timeout=120 --asyncio-mode=auto

# Test hybrid search (should still work)
CLOUD_RUN_URL=https://agentic-hybrid-search-375500751528.us-central1.run.app \
LOGIN_PASSWORD=$(grep '^LOGIN_PASSWORD=' ../.env | cut -d= -f2) \
PYTHONPATH=. python -m pytest \
  tests/e2e/test_deployment_smoke.py::TestSearchPipeline \
  -v -ra --tb=short --timeout=120 --asyncio-mode=auto
```

## Success Criteria

✅ **Run #159 Status**: PASSED (all tests green)  
✅ **Data test**: `test_product_brand_attribute_accessible` PASSED  
✅ **Service health**: `/api/health` returns ok status  
✅ **Error rate**: <1% in logs  
✅ **Latency**: 10-50ms for reranker (confirm 50x improvement)  
✅ **Event emission**: WebSocket clients receive response events consistently  

## Rollback Plan (If Needed)

If any critical tests fail or service issues arise:

```bash
# Revert to previous deployment (if necessary)
gcloud run services update agentic-hybrid-search \
  --set-env-vars=RERANKER_TYPE=gemini \
  --region=us-central1 \
  --project=gen-lang-client-0250737934

# Or restore from backup Cloud Run service
# (Requires prior snapshot/backup)
```

## Issue Resolution

### Issue #15 (Cross-Encoder Reranker)
- ✅ Implementation complete (PR #18 merged)
- ✅ Environment variables fixed (commit f67ffbc)
- ⏳ Deployment validation in progress (Run #159)
- 📋 Latency improvement: Pending measurement post-deployment

### Issue #17 (Citations Missing)
- ✅ Fixed via adaptive score rescaling (PR #18)
- ✅ Agent node citations path validated by smoke tests
- ⏳ Data test validation in progress

### Issue #16 (Empty Response Events)
- ✅ Root cause identified and fixed (commit 5e71a51)
- ⏳ Testing in progress (Run #159)

### Issue #20 (LLM Agent Conversational Tone)
- 📋 Created for future enhancement
- Not blocking deployment

## Next Steps After Validation

1. If all tests pass:
   - Deploy cross-encoder reranker to production stable
   - Monitor metrics for 24-48 hours
   - Document latency improvement in issue #15

2. If issues remain:
   - Investigate root cause of remaining failures
   - May need additional defensive code for empty LLM responses
   - Consider whether brand search queries need special handling

3. Administrative:
   - Update GitHub issues with deployment status
   - Close issues #15 and #17 if fully resolved
   - Schedule latency review in 1 week
