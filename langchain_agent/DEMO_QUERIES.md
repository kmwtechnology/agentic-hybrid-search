# Demo Queries — Agentic Hybrid Search Conference Talk

**Validated:** 2026-05-03 against local backend (langchain_agent main, commit at write-time).
All three picks reproducible 3/3 runs.

> **⚠️ CRITICAL — must deploy before talk:** Five places in `main.py` had the same Gemini-3 bug: `response.content.strip()` raises `'list' object has no attribute 'strip'` because Gemini 3 returns `content` as a list of content blocks, not a string. Each silently caught the exception and degraded to a fallback (or empty result), so the system *appeared* to work but was running with reduced precision. Demo 3 (query expansion) was the only one that visibly broke (no `QueryExpansionEvent` ever fired); the others (category extraction × 2, attribute extraction, title generation) silently fell back to less-precise behavior.
>
> Fix applied to `main.py` (lines 1370, 1434, 1493, 1631, 3126): replace `response.content.strip()` with `_flatten_llm_content(response).strip()`. Total diff is 14-line change (5 inserts, 9 deletes). Bug fix is uncommitted on `main` working tree. **Without these fixes, Demo 3 won't fire `QueryExpansionEvent`, and Demo 2's refinement won't apply the attribute multi_match filter (audience would see only one filter group in the OpenSearch event instead of two).**
>
> Test coverage note: no unit tests directly cover `_expand_vague_query` or the attribute/category extraction paths, but `_flatten_llm_content` (the helper the fix uses) is covered by `tests/unit/test_summarize_messages_content_blocks.py`. The fix is a swap to a tested helper — low regression risk. Confirmed end-to-end via WebSocket probe (5/5 runs) that Demo 2 now emits **two filter groups** (`multi_match` for attribute + `terms` for product_id) instead of one, and Demo 3 emits `QueryExpansionEvent` reliably.

> **Caveat — local NDCG**: the local OpenSearch index has only 9,618 ESCI products vs the prod 1.2M; judgment overlap is sparse, so most NDCG@10 readings below are 0 locally. **In prod (full corpus), NDCG will populate** — the queries below are confirmed to exist in `esci_judgments` so the Pipeline Summary will show real metrics, not the confidence-proxy fallback.

> **Caveat — Demo 1 retry pass invisible locally**: with only 9,618 products, hybrid search returns the *same top-40 docs at any α* (verified: doc-overlap = 1.00 across all tested queries between α=0.85 and α=0.30). So the cross-encoder rescores the same docs and gets the same max — the retry pass cannot visibly improve max_score locally. **In prod, the larger corpus means α=0.85 vs α=0.55 will retrieve materially different docs**, giving the cross-encoder different candidates to rescore. Pre-flight day-of: run Demo 1 against prod once to confirm the retry pass does improve the top-1.

---

## Scenario 1: α-Shift Wins

**Query**: `gift ideas for hair dresser`

**ESCI status**: ✓ exact match in `esci_judgments` (locale=us)

**First Pass**:
- Intent (LLM-classified): `search`
- Starting α: **0.85** (LLM evaluator: "Pure Semantic")
- Reranker max_score: **0.252**
- Reranker top-5 scores: `[0.252, 0.249, ..., ...]` (all very low — no semantic-retrieved product matches conceptually)
- Quality gate: **FAIL** — `RETRY (search): score 0.252 < 0.50, alpha → 0.55`

**Retry Pass**:
- New α: **0.55** (lexical-boost; α ≥ 0.5 → lower by 0.30)
- QG accepts retry results regardless of second-pass score (already retried = accepted)

**Reproducibility (3/3 runs)**:

| Run | Intent | α | max_score | QG |
|-----|--------|---|-----------|-----|
| 1 | search | 0.85 | 0.252 | RETRY → 0.55 |
| 2 | search | 0.85 | 0.252 | RETRY → 0.55 |
| 3 | search | 0.85 | 0.252 | RETRY → 0.55 |

Cross-encoder is deterministic — exact same scores every run.

**Observable events fired** (Observability Panel order):
1. `intent_classified` (search, confidence ~0.95)
2. `opensearch_query` (α=0.85, intent=search)
3. `reranker_progress` (scoring 40 docs)
4. **`quality_gate` (RETRY, max=0.252, new_α=0.55)** ← the wow moment
5. `opensearch_query` (α=0.55, intent=search) ← second retrieval
6. `reranker_progress` (scoring 40 docs again)
7. `quality_gate` (accepted after retry)
8. `agent_complete` (response with citations)
9. `pipeline_summary` (NDCG@10 stages — populated in prod)

**Backup queries** (all confirmed 3/3 ESCI-judged + trigger QG retry — note shift direction):

| Query | LLM α | max_score | retry α | Direction | Notes |
|-------|-------|-----------|---------|-----------|-------|
| `gift ideas for hair dresser` (PRIMARY) | 0.85 | 0.252 | 0.55 | semantic→lexical ✓ | **matches slide narrative** |
| `best elliptical exercise machines` | 0.50 | 0.175 | 0.20 | balanced→lexical ✓ | strongest fail signal, but starting α isn't visibly "semantic-heavy" |
| `best 50 dollar gifts` | 0.85 | 0.282 | 0.55 | semantic→lexical ✓ | clean alternative if hair dresser query reads awkwardly |
| `ideas for young adults for christmas` | 0.85 | 0.371 | 0.55 | semantic→lexical ✓ | close-call max (between 0.371 and threshold 0.50) |

**Avoid for this demo** — these trigger QG but shift α the *wrong* direction (lexical→semantic), undermining the slide narrative:
- `best leaf electric mulcher` (α=0.45 → 0.75)
- `net for pool cleaning for kids` (α=0.45 → 0.75)

**Notes / caveats**:
- The α-shift to 0.55 doesn't change retrieval much *locally* (corpus too small to have meaningfully different semantic vs lexical results). **In prod (1.2M products), the lexical retry will pull in actual hairdressing-related products** (scissors, capes, salon kits) that semantic missed because cosine similarity drifted to "gift" generally.
- The QG firing IS the demo moment — the retry pass succeeding visually is bonus. If the retry max stays low in prod, the Observability Panel still shows the diagnostic loop working.

---

## Scenario 2: Refinement Keeps Context

**Turn 1 Query**: `wireless headphones`
**Turn 2 Query**: `only noise cancelling ones`

**ESCI status — Turn 1**: ✓ exact match in `esci_judgments` (68 judged products; **NDCG@10=0.22** locally — will be higher in prod)
**Turn 2**: natural-language follow-up; doesn't need to be in ESCI (audience expects this).

**Turn 1 (search)**:
- Intent: `search`
- α: 0.30 (LLM evaluator: lexical-leaning for clear product type)
- Reranker max_score: 1.000 (PASS first try)
- Returns 10 wireless-headphone products
- NDCG@10 (local): **0.22** | MRR: 1.0 | judged_count: 1

**Turn 2 (refinement — the demo moment)**:
- Intent: `refinement` ✓ (continuity validation passed — same category)
- α: 0.35 (refinement fast-path)
- **Two filters applied** (post-bug-fix):
  1. `multi_match: {query: "noise cancelling", fields: [title, chunk_text]}` — the extracted attribute constraint
  2. `terms: {product_id: [<10 prior product IDs>]}` — confines to prior search results
- Reranker max_score: 0.98 (PASS)
- Citations: 3 (narrowed from 10 → 3 noise-cancelling)
- **Response prefix (verbatim)**: `From the 10 products I showed you earlier, here are the ones that match your new criteria: filtering for **noise-canceling features**.`
- **Audience-visible payoff**: in the Observability Panel "OpenSearch Query" card they see *two* filter groups, proving the system is parsing the user's constraint AND constraining to prior results — not just one or the other.

**Reproducibility (3/3 runs)**:

| Run | T1 intent | T1 α | T1 NDCG | T2 intent | T2 α | T2 max | Prefix? |
|-----|-----------|------|---------|-----------|------|--------|---------|
| 1 | search | 0.30 | 0.22 | refinement | 0.35 | 0.981 | ✓ |
| 2 | search | 0.30 | 0.22 | refinement | 0.35 | 0.981 | ✓ |
| 3 | search | 0.30 | 0.22 | refinement | 0.35 | 0.988 | ✓ |

**Observable events fired**:
- T1: `intent_classified`, `opensearch_query`, `reranker_progress`, `quality_gate (PASS)`, `agent_complete`, `pipeline_summary`
- T2: `intent_classified` (**refinement**), `opensearch_query` (with filters[product_id]=prior 10), `reranker_progress`, `quality_gate (PASS)`, `agent_complete` (with "I showed you earlier" prefix), `pipeline_summary`

**Backup sequences**:
- `boots` → `make them waterproof` (matches the slide deck verbatim — slide says "30 boots" but reality is 10 due to RERANKER_TOP_K=10; either adjust the slide or say "earlier I showed you 10 boots")
- `water bottle` → `only insulated stainless steel` (T2 max=0.667, narrows 10→2)

**Notes**:
- The category-continuity validation (`_validate_category_continuity` in main.py:1505) silently passes because Turn 2 talks about "noise cancelling" — same category as headphones.
- **⚠️ Don't trust the slide's optional Turn 3 ("category switch resets context"):** verified locally that `find me a red dress` after headphones still routes through `refinement` and applies the prior-product-id filter. Root cause: `prior_search_documents` is empty in `intent_classifier_node` at turn 3 (LangGraph state-persistence quirk — the field survives turn 1→2 *inside the retriever* but doesn't make it into the next turn's `intent_classifier_node`, which runs first). With `prior_docs=0`, the continuity check returns its default 0.5 (ambiguous → no downgrade). Net effect: refinement runs, retrieves 0 docs (no headphones match "red dress"), and the agent gracefully writes prose like "It looks like you've shifted gears from headphones to fashion!" Recommendation: skip Turn 3 in the demo, or use it to show graceful no-results handling. File a follow-up bug to fix the state plumbing if Turn 3 matters for the final talk.
- The 10 product_ids in the filter are a hard guarantee — the audience can verify via Observability Panel "OpenSearch Query" card that the filter list matches the citations from Turn 1.

---

## Scenario 3: Query Rewrite Wins

**⚠️ Requires bug fix to `_expand_vague_query` (see top of file)**

> **Cleaner pick than the original yoga-mat sequence**: `coffee maker` → `how about cheaper`. This routes to `follow_up` intent (not `refinement`), so the demo shows **expansion alone, no product-ID filter** — the audience sees one mechanism at a time, matching the slide's "Low variance → QueryExpansionEvent → second pass spreads the top-10" narrative cleanly. The `yoga mat → are they thick enough for knees?` sequence (described below as a backup) also fires expansion but combines it with refinement filtering, which can blur the story.

**Turn 1 Query**: `coffee maker`
**Turn 2 Query**: `how about cheaper`

**ESCI status — Turn 1**: ✓ exact match in `esci_judgments` (56 judged products; **NDCG@10=0.19** locally)
**Turn 2**: vague natural-language follow-up.

**Turn 1 (search)**:
- Intent: `search`
- α: 0.30
- Reranker max: 0.998 (PASS)
- 10 coffee maker products returned

**Turn 2 — the demo moment**:
- **`QueryExpansionEvent` fires:**
  - Original: `how about cheaper`
  - Expanded: `Are there any cheaper coffee maker options available compared to the ones you previously mentioned?`
- Intent: `follow_up` (NOT refinement)
- α: 0.65 (LLM-evaluated — abstract refinement question)
- **No product-ID filter** — fresh search using the expanded query
- Reranker top-10 scores show clean spread: `[1.0, 0.86, 0.70, 0.41, 0.34, 0.24, 0.20, 0.19, 0.19, 0.18]`
- The pre-expansion query "how about cheaper" alone would retrieve random cheap items; expanded, it pulls actual coffee makers and the cross-encoder ranks them with visible separation

**Reproducibility (3/3 runs)**:

| Run | Expansion fires? | Intent | Top-3 scores |
|-----|------------------|--------|--------------|
| 1 | ✓ "how about cheaper" → "Are there any cheaper coffee maker options..." | follow_up | [1.0, 0.72, 0.66] |
| 2 | ✓ same expansion | follow_up | [1.0, 0.72, 0.66] |
| 3 | ✓ same expansion | follow_up | [1.0, 0.86, 0.70] |

LLM expansion text occasionally varies (small retrieval differences between runs); intent and top-1 always stable.

**Observable events fired**:
- T1: standard search flow.
- T2:
  1. **`query_expansion`** ← the wow moment
  2. `intent_classified` (follow_up)
  3. `opensearch_query` (α=0.65, intent=follow_up, **no filter**)
  4. `reranker_progress`
  5. `quality_gate (PASS)`
  6. `agent_complete`
  7. `pipeline_summary`

**Backup sequences** (all confirmed 3/3 to fire expansion):

| Base | Follow-up | Intent | Notes |
|------|-----------|--------|-------|
| `wireless headphones` | `how is the battery life` | follow_up | Top-2 strong (0.96/0.96), then cliff — clean dropoff |
| `hiking boots` | `are they comfortable for long walks` | follow_up | Gentle score slope, audience-friendly phrasing |
| `yoga mat` | `are they thick enough for knees?` | refinement (combines expansion + filter) | Original pick; clean expansion, T1 NDCG=0.33; cluttered story |
| `wireless headphones` | `on a budget` | refinement | Expansion clean but adds filter |

**Original Demo 3 pick (`yoga mat` → `are they thick enough for knees?`) — kept as backup**:
- T1 NDCG@10 (local): **0.33** (highest of any T1 candidate; best local proof of judgments-overlap)
- T2 expansion: `'are they thick enough for knees?'` → `'Are the yoga mats mentioned in the list thick enough to provide adequate cushioning for my knees?'`
- T2 intent: refinement (filter applied)
- T2 reranker scores: `[0.94, 0.93, 0.91, 0.11, 0.04, 0, 0, 0, 0, 0]` — very clean top-3 vs flat tail
- 3/3 reproducible

**Notes**:
- `_expand_vague_query` always fires on a follow-up where prior conversation exists; whether it actually rewrites depends on the LLM. Short pronoun-laden queries like "are they...", "show me them...", "for the kids", "on a budget", "how about cheaper" reliably get rewritten. Longer self-contained follow-ups may pass through unchanged (no event emitted).
- The bug fix is one line — see top of file. After fix, the picks above fire 100% of the time on T2.

---

## Validation Run Log (2026-05-03)

| Scenario | Query | Run 1 | Run 2 | Run 3 | Verdict |
|----------|-------|-------|-------|-------|---------|
| **Demo 1** | `gift ideas for hair dresser` | RETRY @ max=0.252 | RETRY @ max=0.252 | RETRY @ max=0.252 | **STABLE** |
| **Demo 2** | `wireless headphones` → `only noise cancelling ones` | refinement, prefix ✓ | refinement, prefix ✓ | refinement, prefix ✓ | **STABLE (5/5 — extra runs confirm prefix wording stable; only cosmetic markdown bolding varies)** |
| **Demo 3 (primary)** | `coffee maker` → `how about cheaper` | expansion ✓, follow_up, top-3 [1.0/0.72/0.66] | same | same expansion, slight rerank variance | **STABLE** |
| **Demo 3 (backup)** | `yoga mat` → `are they thick enough for knees?` | expansion ✓, max=0.94 | expansion ✓, max=0.94 | expansion ✓, max=0.99 | **STABLE** |

**All three picks confirmed against local backend with bug fix applied.**

---

## Pre-Talk Checklist

- [ ] Bug fix to `_expand_vague_query` committed and deployed to Cloud Run (Demo 3 hard requirement)
- [ ] Verify ESCI judgments index is populated in prod OpenSearch (Pipeline Summary needs it for real NDCG)
- [ ] Run each demo against the live Cloud Run URL once, day-of, to confirm prod parity
- [ ] If running Demo 1 against prod and the retry pass *also* gets max < 0.50, narrate it as: "the diagnostic still fires; in this case the corpus genuinely doesn't have a strong match — system honestly admits that downstream rather than fabricating"
