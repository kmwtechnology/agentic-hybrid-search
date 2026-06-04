> **Parent**: [Operations Runbooks](README.md)

# Monitoring & Alerts

## Key Metrics to Watch

| Metric | SLO | Where to Find |
|--------|-----|--------------|
| **Search latency (p95)** | <45s | GCP Cloud Monitoring |
| **WebSocket error rate** | <1% | Cloud Run logs (filter: `error` + `WebSocket`) |
| **Cloud SQL connections** | <50 of 100 max | Cloud SQL Insights |
| **Cloud Run CPU** | <80% | Cloud Run metrics dashboard |
| **Agent timeout errors** | <0.1% | Application logs (filter: `AgentTimeoutError`) |

## GCP Logs Explorer Queries

### Error logs (all errors)
```
resource.type="cloud_run_revision"
resource.service_name="agentic-hybrid-search"
severity >= ERROR
```

### Slow searches (>30s)
```
resource.type="cloud_run_revision"
resource.service_name="agentic-hybrid-search"
jsonPayload.latency_ms >= 30000
```

### WebSocket disconnects
```
resource.type="cloud_run_revision"
resource.service_name="agentic-hybrid-search"
(jsonPayload.event_type="WebSocketDisconnect" OR textPayload=~".*WebSocket.*disconnect.*")
```

### LLM API failures
```
resource.type="cloud_run_revision"
resource.service_name="agentic-hybrid-search"
(jsonPayload.exception_type="LLMError" OR textPayload=~".*LLMError.*")
```

**Access:** [GCP Logs Explorer](https://console.cloud.google.com/logs/query?project=gen-lang-client-0250737934)

## GitHub Actions Monitoring

CI/CD pipeline status: [Actions](https://github.com/kmwtechnology/agentic-hybrid-search/actions)

Key workflows to monitor:
- **`test.yml`** — runs on every PR/push; must be green before merge
- **`build-deploy.yml`** — runs on main only; deploys to Cloud Run
- **`reindex.yml`** — triggered manually or on-demand; re-indexes ESCI data

## Alerting Setup (Cloud Monitoring)

### Alert Policy: High Error Rate

Create an alert in GCP Cloud Monitoring (notification channel: email / Slack):

1. **Condition:** `Error count` for `agentic-hybrid-search` service
2. **Threshold:** >100 errors in 5 minutes
3. **Actions:** Send email + Slack webhook

### Alert Policy: High Latency

1. **Condition:** `Search latency (p95)` > 50 seconds
2. **Threshold:** 5 minutes sustained
3. **Actions:** Page on-call

### Alert Policy: Cloud SQL Connection Pool

1. **Condition:** `Connections` > 80 of max 100
2. **Threshold:** 2 minutes sustained
3. **Actions:** Warning email to DevOps

## Dashboard Setup

Create a Cloud Monitoring dashboard for at-a-glance health:

Panels to include:
- Cloud Run request latency (p50, p95, p99)
- Cloud Run request count by status code
- Cloud Run CPU utilization
- Cloud SQL active connections
- Error rate (queries by error type)

**Template:** See GCP Cloud Run > Services > agentic-hybrid-search > Metrics tab (auto-populated).

## On-Call Runbook

When on-call, check **in this order**:

1. **Cloud Run service status** — Is it running? (should see green checkmark)
2. **Error logs** — `make ci` equivalent errors or new exception types?
3. **Latency logs** — Are searches hanging at a specific node (Retriever? Reranker?)?
4. **Cloud SQL** — Connection pool exhausted? (`gcloud sql instances describe`)
5. **OpenSearch** — Disk space full? Shards unassigned?

If unsure, **rollback** the latest deploy: see [Deployment Rollback](deployment.md#rollback-procedure).
