# End-to-End Test Scenarios

Complete user workflow testing for e-commerce search pipeline across all 5 intent types.

## E2E Test Coverage

### Scenario 1: Search Intent - Product Discovery
**User Story:** "Find wireless headphones under $100"

**Expected Flow:**
1. ✅ **Intent Classification**: Detect "search" intent (confidence: 0.95)
2. ✅ **Query Evaluation**: Select balanced alpha (0.65) via LLM path
3. ✅ **Retrieval**: Hybrid search returns 5-10 relevant products
4. ✅ **Reranking**: Score documents (0.68-0.85)
5. ✅ **Quality Gate**: PASS (max_score 0.72 >= threshold 0.50)
6. ✅ **Agent Response**: 
   - Display product list with features
   - Include prices, ratings, key specs
   - Provide Amazon links
7. ✅ **WebSocket Events**: 
   - intent_classified → query_evaluated → search_progress → reranker_progress → quality_gate → agent_response → completion

**Success Criteria:**
- Returns at least 3 products
- All prices shown with currency
- Response time < 3 seconds
- WebSocket stream completes without errors

---

### Scenario 2: Comparison Intent - Product Comparison
**User Story:** "Compare Sony WH-1000XM5 vs Bose QuietComfort 45"

**Expected Flow:**
1. ✅ **Intent Classification**: Detect "comparison" intent (confidence: 0.98)
   - Keywords: "vs", "compare", "versus" detected
2. ✅ **Query Evaluation**: Use fast-path alpha = 0.60 (~10ms)
   - Semantic-focused search for quality differences
3. ✅ **Retrieval**: Find both products (Sony and Bose)
4. ✅ **Reranking**: Score both products highly (0.80+)
5. ✅ **Quality Gate**: PASS (max_score 0.82 >= threshold 0.55, higher bar for comparison)
6. ✅ **Agent Response**:
   - Feature-by-feature comparison format
   - Price, battery life, noise cancellation, weight, etc.
   - Clear winner indicators per category
   - Recommendation based on priorities
7. ✅ **WebSocket Events**: Distinct comparison-specific event flow

**Success Criteria:**
- Both products found
- Comparison table format used
- All key specifications compared
- Clear visual/text differentiation
- No generic list format (must be comparison)

---

### Scenario 3: Attribute Filter Intent - Filtered Search
**User Story:** "Show me blue wireless headphones under $200"

**Expected Flow:**
1. ✅ **Intent Classification**: Detect "attribute_filter" intent (confidence: 0.96)
   - Attributes detected: color (blue), price (under $200), product_type (headphones)
2. ✅ **Query Evaluation**: Use fast-path alpha = 0.25 (~10ms)
   - Lexical-heavy search for exact specification matching
3. ✅ **Retrieval**: BM25 dominates, returns products matching attributes
4. ✅ **Reranking**: Score matching products highly
5. ✅ **Quality Gate**: PASS (max_score 0.62 >= threshold 0.50)
6. ✅ **Agent Response**:
   - Filtered product list showing:
     * Product name
     * Color (blue)
     * Price (under $200)
     * Matching specifications highlighted
7. ✅ **WebSocket Events**: Filter-specific event annotations

**Success Criteria:**
- Only blue headphones returned
- All under $200
- Specifications clearly shown
- Filtering explicitly mentioned ("Showing results for: Color=Blue, Price<$200")
- Non-matching products excluded

---

### Scenario 4: Follow-Up Intent - Contextual Expansion
**User Story:** User asks "Any cheaper alternatives?" (after searching for headphones)

**Expected Flow:**
1. ✅ **Intent Classification**: Detect "follow_up" intent (confidence: 0.88)
   - Recognizes vague pronoun reference ("any", "those")
2. ✅ **Query Rewriting**: Expand context from conversation history
   - Detects previous search: "wireless headphones under $100"
   - Expands: "Find cheaper wireless headphones alternatives"
3. ✅ **Query Evaluation**: Use LLM-path alpha (0.45)
   - Balanced search considering context
4. ✅ **Retrieval**: Search with expanded query context
5. ✅ **Reranking**: Score budget-friendly options higher (0.65)
6. ✅ **Quality Gate**: PASS (max_score 0.65 >= 0.50)
7. ✅ **Agent Response**:
   - "Based on your previous search for wireless headphones..."
   - Budget options highlighted
   - Price comparisons to previous results
   - Alternative brands suggested
8. ✅ **Query Expansion Event**: Shows original vs expanded query

**Success Criteria:**
- Query expansion visible to user
- Context correctly inferred from history
- Budget-friendly products prioritized
- Cheaper than initial search results
- Response acknowledges previous context

---

### Scenario 5: Summary Intent - Conversation Recap
**User Story:** "Summarize our conversation"

**Expected Flow:**
1. ✅ **Intent Classification**: Detect "summary" intent (confidence: 0.99)
   - Clear intent keyword: "summarize"
2. ✅ **Pipeline Bypass**: Skip retrieval/reranking
   - Focuses on conversation history only
3. ✅ **Agent Response**:
   - Timeline: "You searched for... → You compared... → You filtered by..."
   - Key decisions: Which products were compared, which filters applied
   - Final recommendations: Products discussed, prices, top picks
   - Conversation insights: Preferences identified
4. ✅ **Output Format**: Organized recap with:
   - What was searched (initial queries)
   - Products discussed (names, prices)
   - Comparisons made (differences noted)
   - Final selections or decisions

**Success Criteria:**
- Chronological recap of conversation
- All major interactions included
- Products mentioned are listed with key details
- Comparisons/filters summarized
- Recommendations or conclusions included
- No new retrieval/ranking happens

---

## Quality Gate Retry Scenarios

### Scenario 6A: Retry with Alpha Adjustment (Recovery)
**Condition:** Initial search score too low, triggers retry

1. ✅ **First Attempt**:
   - Query: "comfy hearing aids"
   - Alpha: 0.85 (semantic-heavy)
   - Retrieved score: 0.32 (too low)
   - Quality Gate: RETRY (0.32 < 0.50)

2. ✅ **Alpha Adjustment**:
   - Decrease alpha by 0.3: 0.85 → 0.55 (more lexical)
   - Rationale: Semantic search failing, try lexical matching

3. ✅ **Second Attempt**:
   - Same query, new alpha
   - Retrieved score: 0.58 (improved)
   - Quality Gate: PASS (0.58 >= 0.50)
   - Agent: Provides results with confidence

**Success Criteria:**
- Retry triggered at threshold
- Alpha adjustment applied correctly (±0.3)
- Second attempt produces better results
- User sees improved results
- No infinite retry loop

---

### Scenario 6B: Intent-Specific Threshold
**Condition:** Comparison intent uses stricter threshold (0.55 vs 0.50)

1. ✅ **Search Intent**:
   - Score: 0.52
   - Threshold: 0.50
   - Result: PASS ✅

2. ✅ **Comparison Intent (same score)**:
   - Score: 0.52
   - Threshold: 0.55 (stricter)
   - Result: RETRY (0.52 < 0.55)
   - Alpha adjustment applied
   - Second attempt: Score 0.58 → PASS

**Success Criteria:**
- Comparison has higher bar (0.55 > 0.50)
- Same score treated differently by intent
- User sees quality improvement on retry

---

## Error Scenarios

### Scenario 7: No Documents Retrieved
**Condition:** Retriever finds no matching products

1. **Intent Classification**: ✅ Detects "search"
2. **Retrieval**: ❌ Returns 0 documents
3. **Quality Gate**: No retry (no documents to re-score)
4. **Agent Response**: "No products found matching your criteria"
5. **User Actions**: Refine search with different keywords

**Success Criteria:**
- User gets clear "no results" message
- Suggestions for refinement
- No confusing error states

---

### Scenario 8: Low Confidence Intent Classification
**Condition:** Ambiguous query triggers clarification

**Query:** "Maybe something electronic with buttons?"

1. **Intent Classification**: 
   - Best guess: "search" (confidence: 0.45)
   - Low confidence detected (< 0.7)
2. **Clarification Questions**:
   - "Are you looking for headphones, speakers, or other electronics?"
   - "Do you have a specific budget?"
3. **User Response**: Clarifies search
4. **Pipeline Continues**: With clarified intent

**Success Criteria:**
- Clarification questions appear automatically
- User can provide additional context
- Second attempt with refined query

---

## Concurrent User Scenarios

### Scenario 9: Multiple Simultaneous Searches
**Condition:** Two users searching independently

**User A**: "Compare Samsung and Apple phones"
**User B**: "Find cheap headphones"

**Success Criteria:**
- Both searches process independently
- No cross-contamination of results
- Both receive correct responses
- WebSocket streams don't interfere
- Independent conversation histories

---

## Performance Scenarios

### Scenario 10: Fast-Path Performance
**Condition:** Comparison intent uses fast-path (no LLM)

**Metrics:**
- Query → Alpha Selection: < 10ms (deterministic, no LLM call)
- Search → Rerank: < 1s
- Quality Gate: < 50ms
- Total: < 1.5s (no LLM latency)

**Vs LLM-Path (Search Intent):**
- Query → Alpha Selection: 2-3s (LLM evaluation required)
- Search → Rerank: < 1s
- Quality Gate: < 50ms
- Total: 3-4s

**Success Criteria:**
- Fast-path (comparison) < 1.5s
- LLM-path (search) < 4s
- Clear performance benefit from fast-path

---

## State Persistence Scenarios

### Scenario 11: Conversation Continuity
**User Session:**
1. Search 1: "Find blue headphones"
2. Search 2: "Compare two of them"
3. Follow-up: "Any cheaper options?"
4. Summary: "Recap what we discussed"

**Requirements:**
- All queries maintain context
- Conversation history preserved
- Previous products available for comparison
- Summary includes all interactions

**Success Criteria:**
- No loss of conversation history
- Context properly passed between queries
- Summary accurate and complete

---

## Metrics & Assertions

### Response Quality Metrics
```
Search Intent:
- Precision: >= 80% (relevant products)
- Response Time: < 3s
- Document Count: 3-10 products

Comparison Intent:
- Accuracy: Both products found
- Format: Comparison table
- Response Time: < 1.5s (fast-path)

Attribute Filter:
- Recall: 100% of matching products
- Filtering: 100% accuracy
- Response Time: < 2s

Follow-Up Intent:
- Context Resolution: 95%+ accuracy
- Relevance: >= 85%
- Response Time: < 3s

Summary Intent:
- Completeness: All interactions covered
- Accuracy: Correct product info
- Response Time: < 1s
```

---

## Test Implementation

### Tools Required
- Playwright or Cypress for browser automation
- API client (axios/fetch) for backend testing
- WebSocket test client for event stream validation

### Test Data
- Test products: Sony WH-1000XM5, Bose QC45, etc.
- Test queries: Pre-defined for each intent
- Conversation history: Seeded before tests

### CI/CD Integration
```bash
# Run all E2E tests
npm run test:e2e

# Run specific intent tests
npm run test:e2e -- --grep "search"
npm run test:e2e -- --grep "comparison"

# Generate report
npm run test:e2e:report
```

---

## Summary

**Total E2E Scenarios: 11**
- 5 Happy path scenarios (one per intent)
- 2 Quality gate retry scenarios
- 2 Error scenarios
- 1 Concurrent user scenario
- 1 Performance scenario
- (+Conversation continuity)

**Assertion Count: 50+**
**Expected Test Duration: < 5 minutes total**
**Success Rate Target: 100%**

These E2E tests validate the complete e-commerce search pipeline with real-world user scenarios and edge cases.
