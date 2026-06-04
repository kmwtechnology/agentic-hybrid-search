> **Parent**: [Operations Runbooks](README.md)

# Scaling Guide

## Cloud Run Configuration

### Concurrency & Instance Count

| Setting | Value | Rationale |
|---------|-------|-----------|
| **Concurrency** | `1` | WebSocket sessions are stateful; each request must stick to the same container |
| **Max instances** | `10` | Limit to control costs; one search ≈ 1 min, so 10 instances ≈ 10 concurrent searches |
| **Min instances** | `0` (cold start) or `1` (warm) | `0` to save cost (~$7/month); `1` if <1s latency required (~$10/month) |
| **Memory** | `2 Gi` | Default sufficient; increase to `4 Gi` if `RERANKER_FETCH_K > 30` |
| **CPU** | `2` | Default; increase to `4` for very high throughput (rare) |

### Tuning Concurrency = 1

**Why?** WebSocket connections are per-instance. If concurrency > 1, one instance serves multiple concurrent users, risking shared state pollution (though the code is thread-safe, it's conservative to isolate).

**To change:**
```bash
gcloud run services update agentic-hybrid-search \
  --region=us-central1 \
  --concurrency=1
```

### Cost Math

- Base: **$0.00002400 per vCPU-second** + **$0.0000050 per GB-second**
- Typical: 2 vCPU, 2 GB RAM
- 1 search ≈ 1 minute → ~$0.005 per request
- Min instance (always-on): ~$10/month

---

## Database Scaling

### Cloud SQL Connection Pool

| Metric | Threshold | Action |
|--------|-----------|--------|
| Active connections | >80 of 100 | Increase `max_connections` or reduce Cloud Run max instances |
| Connection wait time | >100ms | Scale down other workloads; upgrade Cloud SQL tier |

**To increase max connections:**
```bash
gcloud sql instances patch agentic-hybrid-search \
  --database-flags=max_connections=150
```

### Cloud SQL Memory & CPU

Monitor via Cloud SQL Insights. If CPU >80% sustained:

1. Upgrade instance class: `db-f1-micro` → `db-n1-standard-1`
2. Add a read replica for read-heavy analytics queries (if applicable)

---

## OpenSearch Scaling

### Shard & Node Scaling

If search queries are slow (>30s) with low errors:

1. **Check shard count:** Each shard should have <10M documents
   ```
   curl http://localhost:9200/agentic_hybrid_search_docs/_stats
   ```
2. **Increase shards if needed:**
   ```bash
   curl -X PUT http://localhost:9200/agentic_hybrid_search_docs/_settings \
     -H "Content-Type: application/json" \
     -d '{"index": {"number_of_shards": 5}}'
   ```
3. **Add nodes to cluster** if CPU/memory exhausted

### HNSW Vector Index Parameters

The index uses HNSW for kNN search. Tuning is rare, but if k-NN latency is high:

```json
"index.knn": true,
"index.knn.algo_param.ef_search": 512
```

Increase `ef_search` (default 512) for higher recall at cost of latency. Typical: 512 or 1024.

---

## Caching & Performance

### Embedding Cache

Cold embeddings (first request): require an API call to Gemini (~200ms per query).

Warm embeddings (cached): <1ms lookup.

The embedding cache is in-memory per instance and per-process. To pre-warm:

1. Submit N queries (typical: 10–20)
2. Subsequent requests for similar queries hit cache

### Checkpoint Cache

LangGraph checkpoints are stored in PostgreSQL. Retrieval is O(1) per checkpoint. No scaling needed unless checkpoint table grows to >1B rows (extremely rare).

---

## Load Testing

Before scaling to production traffic:

1. **Local smoke test:** `make smoke-local` (20 tests, ~90s)
2. **GCP smoke test:** `make smoke-local` but pointed at Cloud Run URL
   ```bash
   CLOUD_RUN_URL=https://agentic-hybrid-search-xyz.run.app \
     LOGIN_PASSWORD=... \
     pytest tests/e2e/ -m "e2e and slow" --timeout=120
   ```
3. **Gradual traffic increase:** Deploy with `min_instances=1`, monitor for 24h, then scale up

---

## Cost Optimization

| Lever | Impact | Effort |
|-------|--------|--------|
| Set `min_instances=0` (cold start OK) | Save $10/mo | Trivial; accept 15s cold-start latency |
| Reduce `max_instances` to 5 | Save $/mo per concurrent user over 5 | Depends on traffic; could cause 503 overload |
| Use Spot VMs for Cloud SQL (if non-prod) | Save 70% | Only for non-critical; restarts lose connections |
| Pre-compute embeddings batch (not real-time) | N/A for real-time search | Different use case |

---

## Monitoring for Scale Issues

Add alerts (see [Monitoring](monitoring.md)):

- ✅ Error rate spike → rollback
- ✅ Latency >60s sustained → scale up instances or optimize config
- ✅ Cloud SQL connections >80 → scale up DB or reduce max instances
- ✅ Cloud Run CPU >90% → increase CPU or concurrency

---

## Example: Scaling from 1 → 100 concurrent users

Assumptions:
- Each search = 1 minute
- Concurrency = 1
- 100 concurrent users → need ~100 instances

Steps:

1. **Increase `max_instances`:**
   ```bash
   gcloud run services update agentic-hybrid-search --max-instances=100
   ```

2. **Ensure Cloud SQL can handle 100 connections:**
   ```bash
   gcloud sql instances patch agentic-hybrid-search \
     --database-flags=max_connections=150
   ```

3. **Upgrade Cloud SQL if needed:** Monitor CPU/memory; upgrade to `db-n1-standard-2` if >80% utilized

4. **Monitor for 24h:** Set alarms on error rate, latency p95, and database connection pool

5. **Cost estimate:** 100 instances × $0.005/search × 100 searches/day ≈ $50/day
