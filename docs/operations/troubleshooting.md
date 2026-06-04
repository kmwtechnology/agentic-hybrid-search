> **Parent**: [Operations Runbooks](README.md)

# Troubleshooting Guide

## General Patterns

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Service won't start (CrashLoopBackOff) | Missing required env var | Check Cloud Run logs; see "Startup Errors" below |
| 500 errors spiking | New code regression OR external API down | Check error logs; if new, rollback; if external, wait or switch fallback |
| WebSocket connections drop | Client network OR container restart | Transient: client auto-reconnects; sustained: check Cloud Run health |
| Search latency >60s | Cold start OR reranker model loading | Expected on first request after deploy; subsequent requests <30s |
| Memory limit exceeded | FETCH_K too high OR batch size too large | Reduce `RERANKER_FETCH_K` in .env; Cloud Run memory default 2GB |
| OpenSearch index not found | Lucille ETL failed OR wrong index name | Re-trigger `reindex.yml` workflow; verify `OPENSEARCH_INDEX_NAME` env var |
| Database connection refused | Postgres not running OR connection pool exhausted | Local: `docker compose up -d`; Cloud: check Cloud SQL network access |

## Startup Errors (Service Won't Boot)

### ConfigurationError on startup

```
ConfigurationError: Missing required environment variable: GOOGLE_API_KEY
```

**Fix:**
1. Get key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Add to Secret Manager: `gcloud secrets create GOOGLE_API_KEY --data-file=- <<< "sk-..."`
3. Redeploy: `./scripts/deploy.sh --project gen-lang-client-0250737934`

### Connection timeout (PostgreSQL)

```
psycopg.OperationalError: could not connect to server: Connection timed out
```

**Fix:**
1. Verify Cloud SQL instance running: `gcloud sql instances describe agentic-hybrid-search`
2. Check network access: Cloud SQL > Connections > Public IP (Cloud Run's egress IP in allow-list?)
3. Check password in Secret Manager matches actual password
4. Restart Cloud SQL: `gcloud sql instances restart agentic-hybrid-search --async`

### OpenSearch connectivity

```
OpenSearchError: error connecting to OpenSearch: Connection refused
```

**Fix:**
- Local: `docker compose up -d` to start OpenSearch
- Cloud: Verify OpenSearch VM is running and IP is accessible from Cloud Run VPC

## Memory Issues (Out of Memory / Killed)

**Symptom:** Cloud Run revision suddenly stops processing, crashes with exit code 137.

**Root cause:** `RERANKER_FETCH_K` too high (default 40; each document loads full cross-encoder model in memory).

**Fix:**
1. Reduce `RERANKER_FETCH_K` to 20 in `.env`
2. Or increase Cloud Run memory: `--memory=4Gi` in deploy.sh
3. Redeploy and test: `./scripts/deploy.sh --project gen-lang-client-0250737934`

## Latency Issues

### First request after deploy takes >60s

**Expected behavior** — the LLM models and cross-encoder are cold-loaded. Subsequent requests <30s.

**Workaround:** Add Cloud Run `min_instances=1` to keep container warm (costs $~10/month per instance).

### All searches slow (latency spike)

**Checks:**
1. Is OpenSearch reachable? → Run Logs Explorer query for network timeouts
2. Is Cloud SQL responding? → Check active connections (should be <50)
3. Is FETCH_K too high? → Default is 30; if you changed it, lower to 15
4. Is reranker stuck? → Check logs for `RerankerError` or timeouts

**Remediation:**
1. If recent deploy: `gcloud run services update-traffic ... --to-revisions=PREVIOUS=100` (rollback)
2. If infrastructure: check Cloud SQL / OpenSearch metrics
3. If config: adjust `FETCH_K`, `RERANKER_FETCH_K`, or `LLM_TEMPERATURE`

## WebSocket Connection Issues

### Clients disconnect with code 4401 (Unauthorized)

**Cause:** Session cookie expired OR admin token invalid.

**Fix:** Clients must re-login via `POST /api/auth/login` or refresh their admin token.

### WebSocket handshake fails (403 Forbidden)

**Cause:** Origin header mismatch or session not present.

**Fix:**
1. Verify request includes Origin header AND valid session cookie OR X-Admin-Token header
2. Check allow-list in `api/middleware/origin_auth.py`: should include your client domain
3. If localhost, ensure port is in `ALLOWED_ORIGINS` (check `.env`)

## Cloud Run Cold Start Latency

**Symptom:** First request after deploy or long idle period takes 15–20 seconds.

**Root cause:** Container startup + model loading (LLM + embeddings + cross-encoder).

**Options:**
1. Accept it (cold start expected; document as SLO: 45s)
2. Set `min_instances=1` to keep container warm (costs $)
3. Pre-warm with a dummy request on deploy (see `deploy.sh` smoke tests)

## Re-indexing Failures

### Lucille ETL fails with Java exception

```
Exception in thread "main" java.lang.Exception: Failed to build Lucille index
```

**Fix:**
1. Ensure Java 17+ installed: `java -version`
2. Ensure Maven cache clean: `mvn clean -D maven.repo.local=...`
3. Re-trigger workflow: `gh workflow run reindex.yml`
4. Check workflow logs in Actions tab

### Index query returns 0 results after re-index

**Cause:** Index mapping mismatch OR `collection_id` not set on documents.

**Fix:**
1. Verify `collection_id=esci_products` is set on all documents (check via `curl http://localhost:9200/agentic_hybrid_search_docs/_search`)
2. Run `lucille_ingest.sh` with `--reset-index` flag to rebuild from scratch

## Network & Firewall

### Cloud Run service unreachable

**Checklist:**
- [ ] Service ingress set to "Allow public traffic"? (Cloud Run > Services > agentic-hybrid-search > Edit > Ingress)
- [ ] Firewall rules allow port 443? (VPC > Firewall)
- [ ] Service URL correct? (e.g., `https://agentic-hybrid-search-xyz.run.app`)

### Cloud SQL connection refused from Cloud Run

**Fix:**
1. Verify Cloud SQL Public IP or Private IP connectivity
2. If using Private IP, ensure Cloud Run is in the same VPC
3. Add Cloud Run service account to Cloud SQL client connections in IAM

---

**Still stuck?** Escalate to [GitHub Issues](https://github.com/kmwtechnology/agentic-hybrid-search/issues) or check the [Deployment History](../../../.claude/projects/-Users-kevin-github-kmwtechnology-agentic-hybrid-search/memory/deployment_history.md) for past incidents.
