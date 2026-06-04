> **Parent**: [Contributing Guide](README.md)

# PR Process

Guidelines for branching, commits, PR body, and self-review.

---

## Branch Naming

Use this format:

```
feat/{issue-number}-{slug}    # New feature
fix/{slug}                     # Bug fix
docs/{slug}                    # Documentation
chore/{slug}                   # Refactoring, cleanup
test/{slug}                    # Test improvements
```

**Examples:**
```
feat/issue-28-swagger-localhost-fix
fix/websocket-reconnection-deadlock
docs/add-operations-guide
chore/cleanup-dead-code
```

---

## Commits

**Style:** Conventional Commits with optional ticket prefix

```
{optional-ticket-id} {type}: {subject}

{body}

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Types:** `feat`, `fix`, `docs`, `chore`, `test`, `perf`, `refactor`

**Example:**
```
#54 fix: correct exceptions in quality gate retry logic

The quality gate was catching bare Exception instead of specific
exception types, making error logs ambiguous. Now catches LLMError
and SearchTimeoutError explicitly with distinct log messages.

All 708 unit tests pass. Smoke-local-quick passes.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**One commit per logical concern.** If your PR fixes two bugs, make two commits.

---

## PR Body Template

**Use this template when opening a PR:**

```markdown
## Summary

One-liner describing what changed and why.

## What

- Bullet list of what was changed
- Why it needed to change
- Any design decisions

## Testing

- [ ] Unit tests pass: `PYTHONPATH=. pytest tests/unit/`
- [ ] Smoke test passes: `make smoke-local-quick`
- [ ] CI passes: `make ci`
- [ ] Manual testing (if applicable): describe what you tested

## Rollout

- No database migrations
- No env var changes
- No breaking API changes

---

Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Self-Review Checklist

Before requesting review, go through this checklist:

### Code Quality

- [ ] No stale comments or TODOs
- [ ] No dead code (removed imports, unused variables)
- [ ] No hardcoded values (use env vars or constants)
- [ ] Consistent with project style (black, isort, flake8 pass)
- [ ] Type hints present where applicable (mypy clean)

### Backend Changes

- [ ] No bare `except Exception` (use specific exception types from `exceptions.py`)
- [ ] State access uses `.get(field, default)` pattern
- [ ] All `agent_node` return paths include `"citations"` key
- [ ] Event parity test passes: `pytest tests/unit/test_frontend_backend_event_parity.py -v`
- [ ] New exceptions inherit from `AgenticHybridSearchError`

### Frontend Changes

- [ ] TypeScript types match backend events (`web/src/types/events.ts`)
- [ ] Frontend eslint and tsc clean
- [ ] `npm test` passes

### Documentation

- [ ] README files updated if you added/changed directory structure
- [ ] New endpoints or parameters documented
- [ ] Links in README/docs use correct relative paths
- [ ] No broken internal links (test with `grep -r "\.\./\.\." docs/`)

### Deployment

- [ ] Env vars set in BOTH `scripts/deploy.sh` AND `build-deploy.yml --set-secrets` (if needed)
- [ ] No secrets committed (check `.gitignore`)
- [ ] Cloud Run memory/CPU config updated if needed

### Tests

- [ ] Unit tests pass: `PYTHONPATH=. pytest tests/unit/ -v`
- [ ] Integration tests run locally: `PYTHONPATH=. pytest tests/integration/ -v`
- [ ] Smoke tests pass: `make smoke-local` (if backend path changed)
- [ ] E2E tests pass locally: `CLOUD_RUN_URL=http://localhost:8000 pytest tests/e2e/ -m "not slow" -v`

---

## Review Expectations

**All PRs require at least 1 approval before merge.**

- Small changes (<100 lines, docs-only): Fast approval
- Code changes: Expect 1–2 rounds of feedback
- Infrastructure changes: Expect careful review

**Comment response:** Reply to every comment either with a fix commit or a brief written explanation. If feedback conflicts with prior decisions, note the tension in the reply (don't silently drop feedback).

---

## Before Pushing

1. Run `make ci` — all linters, tests, type checks must pass
2. Run `make smoke-local` (if backend changes) — sanity check against local backend
3. Read the diff end-to-end: `git diff main`
4. Verify all links resolve (docs PRs): `grep -r "\.\./\.\." docs/`
5. Check for secrets in the diff: no `.env`, API keys, tokens

```bash
# Full checklist
make ci
make smoke-local
git diff main | grep -E "password|api.?key|token|secret" && echo "FOUND SECRETS!" || echo "No secrets found"
```

---

## Merge & Deploy

**Merge:** Squash to `main` after review approval + CI green.

```bash
gh pr merge <PR_NUMBER> --squash
```

**Deployment:** On `main`, GitHub Actions automatically:
1. Runs full CI
2. Builds Docker image
3. Pushes to Artifact Registry
4. Deploys to Cloud Run
5. Runs smoke tests

Monitor the deploy in [Actions](https://github.com/kmwtechnology/agentic-hybrid-search/actions).

---

## Troubleshooting

### Pre-commit hook blocks commit

Hook failed (usually black/isort):

```bash
cd langchain_agent && make format-fix
git add .
git commit --no-verify  # Finish the commit bypassing the hook
```

Then re-run the hook to verify:

```bash
.git/hooks/pre-commit
```

### Pre-push hook blocks push

Smoke tests failing. Run them locally and fix:

```bash
make smoke-local  # See what failed
# Fix the issue
git add .
git commit -m "fix: ..."
git push
```

### CI fails on GitHub but passes locally

Likely causes:
- Different Python version (`python3 --version` should be 3.13)
- Different Node version (`node --version` should be 24)
- Missing env vars in Secret Manager

Check the GitHub Actions log for details.

---

## Working Session 14-Step Rhythm

This project follows a 14-step workflow (simplified here):

1. **Discuss** — review memory, prior PRs; restate scope
2. **Plan** — propose approach, get approval for non-trivial work
3. **Code** — create branch, write code
4. **Test** — run unit + smoke + integration tests locally
5. **Commit** — let pre-commit hooks run; one logical commit per concern
6. **Update docs/memory** — refresh this file and any affected READMEs
7. **Push & open PR** — open as draft; add Why/What/Testing body
8. **CI watch** — `gh pr checks <num>`; fix failures
9. **Self-review** — read diff end-to-end against checklist above
10. **Ready for review** — `gh pr ready <PR>`
11. **Address feedback** — commit fixes (don't force-push); re-request review
12. **Merge** — squash to main after approval + CI green
13. **Post-deploy** — watch deploy workflow; verify in target environment
14. **Cleanup** — close tickets, archive in Obsidian

**Full rhythm:** See `~/.claude/working-session-workflow.md` (global instructions).
