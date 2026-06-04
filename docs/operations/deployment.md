> **Parent**: [Operations Runbooks](README.md)

# Deployment Checklist & Procedures

## Pre-Deploy Checklist

Before running the deploy script, verify:

| Check | Command | Notes |
|-------|---------|-------|
| **Code on main** | `git status` | All changes merged to main |
| **CI green** | GitHub Actions | All workflows passing on main |
| **Smoke test pass** | `make smoke-local` | Full 20-test suite must pass locally |
| **Env vars in deploy.sh** | `grep -c 'gcloud run services update --set-env-vars' scripts/deploy.sh` | Both config AND secrets set |
| **Env vars in build-deploy.yml** | `grep -c 'set-secrets' .github/workflows/build-deploy.yml` | Secrets synchronized with .env |
| **GCP auth ready** | `gcloud auth application-default print-access-token` | No "unauthorized" errors |
| **GCP project set** | `gcloud config get-value project` | Correct `gen-lang-client-0250737934` |

## Deploy Command

From repo root:

```bash
./scripts/deploy.sh --project gen-lang-client-0250737934
```

What it does:
1. Builds Docker image locally (or uses cached layer from prior build)
2. Pushes to `us-central1-docker.pkg.dev/<PROJECT_ID>/agentic-hybrid-search/agentic-hybrid-search:latest`
3. Updates Cloud Run service with new image
4. Performs blue-green traffic split (described below)
5. Runs `/health` smoke tests on the deployed service

Expected time: **3–5 minutes** (15s build, 30s push, 90s deploy, 2m smoke tests).

## Blue-Green Deployment

Cloud Run automatically creates a new revision. Traffic gradually shifts:

1. New revision spins up with new image
2. Both old and new revisions serve traffic briefly (canary window, ~30s)
3. Once health checks pass, 100% traffic routes to new revision
4. Old revision stays available for rollback (see below)

**No downtime** — WebSocket connections on old revision continue until client disconnect/reconnect.

## Rollback Procedure

If the new revision has issues:

```bash
gcloud run services update-traffic agentic-hybrid-search \
  --region=us-central1 \
  --to-revisions=PREVIOUS=100
```

This routes 100% traffic back to the previous (pre-deploy) revision **instantly**. Current sessions on the broken revision will disconnect and reconnect to the old one.

To check current traffic split:

```bash
gcloud run services describe agentic-hybrid-search \
  --region=us-central1 \
  --format='value(status.traffic[].percent)'
```

## Monitoring Deployment Progress

Watch logs in real-time:

```bash
gcloud run services logs read agentic-hybrid-search \
  --region=us-central1 \
  --project gen-lang-client-0250737934 \
  --limit 50 \
  --follow
```

Or in GCP Cloud Console: [Cloud Run Services](https://console.cloud.google.com/run?project=gen-lang-client-0250737934)

## Re-indexing After Deploy

To re-index ESCI data on the deployed Cloud Run instance (without redeploying):

```bash
gh workflow run reindex.yml --repo kmwtechnology/agentic-hybrid-search
```

This:
1. Clones the Lucille external repo
2. Runs Lucille ETL on the hosted OpenSearch instance
3. Rebuilds the full `agentic_hybrid_search_docs` index (~2–3 minutes)

**Note:** Re-indexing does NOT trigger a Cloud Run deploy; the running service remains online and briefly serves stale results during the reindex window.

## Deployment Environment Variables

Critical: **env vars must be set in both places**:

1. **`scripts/deploy.sh`** — credentials and config that never change
2. **`.github/workflows/build-deploy.yml`** → `--set-secrets` — values that might rotate (API keys)

See [Required env vars in BOTH deploy paths](../../../.claude/projects/-Users-kevin-github-kmwtechnology-agentic-hybrid-search/memory/feedback_required_env_vars_in_both_deploy_paths.md) for the full list and verification steps.
