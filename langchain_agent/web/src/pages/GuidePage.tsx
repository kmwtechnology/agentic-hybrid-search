/**
 * Comprehensive guide for Agentic Hybrid Search project.
 * Includes usage, features, examples, and troubleshooting.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface Section {
  id: string
  title: string
  content: React.ReactNode
}

export function GuidePage() {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['intro']))

  const toggleSection = (id: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(id)) {
      newExpanded.delete(id)
    } else {
      newExpanded.add(id)
    }
    setExpandedSections(newExpanded)
  }

  const sections: Section[] = [
    {
      id: 'intro',
      title: '🎯 Welcome to Agentic Hybrid Search',
      content: (
        <div className="space-y-4">
          <p className="text-gray-700">
            This is a production-grade AI-powered e-commerce product search agent that uses hybrid search (semantic + lexical),
            intelligent reranking, and real-time observability to help users find and compare products.
          </p>
          <div className="bg-blue-50 border-l-4 border-blue-500 p-4">
            <h4 className="font-semibold text-blue-900 mb-2">Key Capabilities</h4>
            <ul className="text-blue-800 space-y-1 text-sm">
              <li>✓ Natural language product search</li>
              <li>✓ Product comparison and attribute filtering</li>
              <li>✓ Real-time streaming responses with citations</li>
              <li>✓ Conversation memory and resumption</li>
              <li>✓ Per-query search optimization toggles (9 flags) — fuzzy, synonyms, phonetic, phrase boost, field boost, hybrid, typeahead, reranker, LLM</li>
              <li>✓ Pipeline Quality Summary card — offline NDCG/MRR/Recall@20/Precision@10 vs an ESCI ground-truth baseline, with latency cost-benefit framing</li>
              <li>✓ Full pipeline observability with real-time events</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'quickstart',
      title: '⚡ Quick Start',
      content: (
        <div className="space-y-4">
          <div className="space-y-3">
            <h4 className="font-semibold text-gray-900">1. Start the services</h4>
            <pre className="bg-gray-900 text-gray-100 p-3 rounded text-sm overflow-x-auto">
              <code>cd langchain_agent{'\n'}make dev</code>
            </pre>
            <p className="text-sm text-gray-600">This starts the API (port 8000) and frontend (port 5173)</p>

            <h4 className="font-semibold text-gray-900 mt-4">2. Open the UI</h4>
            <p className="text-sm">Visit <a href="http://localhost:5173" className="text-blue-600 hover:underline">http://localhost:5173</a></p>

            <h4 className="font-semibold text-gray-900 mt-4">3. Start asking</h4>
            <p className="text-sm text-gray-600">Try: "What are the best wireless earbuds with active noise cancellation?"</p>
          </div>
        </div>
      ),
    },
    {
      id: 'features',
      title: '✨ Core Features',
      content: (
        <div className="space-y-4">
          <div className="space-y-3">
            <div className="border-l-4 border-green-500 pl-4">
              <h4 className="font-semibold text-gray-900">Hybrid Search</h4>
              <p className="text-sm text-gray-600">Combines semantic (vector) and lexical (BM25) search with automatic tuning based on query type</p>
              <p className="text-xs text-gray-500 mt-1">Example: "Sony headphones" uses 25% semantic, 75% lexical for brand specificity</p>
            </div>

            <div className="border-l-4 border-purple-500 pl-4">
              <h4 className="font-semibold text-gray-900">Intent Classification</h4>
              <p className="text-sm text-gray-600">Automatically understands user intent: search, comparison, filtering, refinement, follow-up</p>
              <p className="text-xs text-gray-500 mt-1">Uses keyword matching + LLM fallback for high confidence (0.7+)</p>
            </div>

            <div className="border-l-4 border-orange-500 pl-4">
              <h4 className="font-semibold text-gray-900">Smart Reranking</h4>
              <p className="text-sm text-gray-600">LLM-based relevance scoring (0.0-1.0) to ensure top results are truly relevant</p>
              <p className="text-xs text-gray-500 mt-1">Quality gate: retries with adjusted search if score &lt; 0.5</p>
            </div>

            <div className="border-l-4 border-pink-500 pl-4">
              <h4 className="font-semibold text-gray-900">Conversation Memory</h4>
              <p className="text-sm text-gray-600">Maintains full message history per thread, smart context management for long conversations</p>
              <p className="text-xs text-gray-500 mt-1">Resume conversations with thread_id; messages stored in PostgreSQL</p>
            </div>

            <div className="border-l-4 border-cyan-500 pl-4">
              <h4 className="font-semibold text-gray-900">Real-time Observability</h4>
              <p className="text-sm text-gray-600">Watch the entire pipeline execute in real-time with typed events</p>
              <p className="text-xs text-gray-500 mt-1">Search → Rerank → Quality Gate → LLM, plus token-by-token streaming</p>
            </div>

            <div className="border-l-4 border-indigo-500 pl-4">
              <h4 className="font-semibold text-gray-900">Search Optimization Toggles</h4>
              <p className="text-sm text-gray-600">Flip any of 9 search features on or off per query and watch the pipeline respond live.</p>
              <p className="text-xs text-gray-500 mt-1">Hybrid · Fuzzy · Synonyms · Phonetic · Phrase boost · Field boost · Typeahead · Reranker · LLM. Skipped stages collapse out of the panel automatically.</p>
            </div>

            <div className="border-l-4 border-yellow-500 pl-4">
              <h4 className="font-semibold text-gray-900">Pipeline Quality Summary</h4>
              <p className="text-sm text-gray-600">End-of-pipeline scorecard rendered as the last card in the Observability panel.</p>
              <p className="text-xs text-gray-500 mt-1">When the query is in ESCI: BM25 → Hybrid → Reranked NDCG@10 / MRR / Recall@20 / Precision@10 with latency lift-per-100ms. Otherwise: a self-referential confidence proxy.</p>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'using-ui',
      title: '💬 Using the Chat UI',
      content: (
        <div className="space-y-4">
          <h4 className="font-semibold text-gray-900">The Three-Panel Layout</h4>
          <div className="grid grid-cols-3 gap-4 my-3">
            <div className="bg-gray-100 p-3 rounded">
              <p className="font-semibold text-sm">Left: Conversations</p>
              <p className="text-xs text-gray-600 mt-1">View, resume, or delete past conversations</p>
            </div>
            <div className="bg-gray-100 p-3 rounded">
              <p className="font-semibold text-sm">Center: Chat</p>
              <p className="text-xs text-gray-600 mt-1">Type questions, see streaming responses with citations</p>
            </div>
            <div className="bg-gray-100 p-3 rounded">
              <p className="font-semibold text-sm">Right: Observability</p>
              <p className="text-xs text-gray-600 mt-1">Watch the pipeline execute step-by-step</p>
            </div>
          </div>

          <div className="space-y-2">
            <h4 className="font-semibold text-gray-900 mt-4">Tips for Best Results</h4>
            <ul className="space-y-1 text-sm text-gray-700">
              <li className="flex gap-2"><span>💡</span> Be specific: "Sony WH-1000XM5 vs Bose QC45" works better than "good headphones"</li>
              <li className="flex gap-2"><span>🎯</span> Use attributes: "blue running shoes size 10" narrows results</li>
              <li className="flex gap-2"><span>🔄</span> Ask follow-ups: "smaller alternatives" or "what about battery life" refines results</li>
              <li className="flex gap-2"><span>📋</span> Click citations to see full product details on Amazon</li>
              <li className="flex gap-2"><span>⚙️</span> Watch the Observability panel to understand why results were ranked this way</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'search-optimizations',
      title: '🎛️ Search Optimization Toggles',
      content: (
        <div className="space-y-4">
          <p className="text-sm text-gray-700">
            The Observability panel exposes 9 per-query toggles that flip individual search features on or off. Changes apply to the <em>next</em> query you send and the panel reflects what actually ran (skipped stages collapse).
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">hybrid</code> — vector + BM25 fusion. Off ⇒ pure BM25.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">fuzzy</code> — adds <code>fuzziness: AUTO</code> to multi_match.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">synonyms</code> — query-time synonym expansion via the <code>english_analyzer</code>.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">phonetic</code> — adds <code>title_phonetic</code> / <code>brand_phonetic</code> fields.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">phrase_boost</code> — adds the <code>title_phrase</code> field with a 2.5× boost.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">field_boost</code> — keeps per-field <code>^N</code> weights. Off ⇒ all fields equal.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">typeahead</code> — frontend autocomplete suggestions.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">reranking</code> — Gemini LLM reranker. Off ⇒ retriever order is final.</div>
            <div className="bg-gray-50 p-2 rounded"><code className="font-mono text-gray-900">llm</code> — agent generation. Off ⇒ deterministic markdown product list.</div>
          </div>

          <div className="bg-blue-50 border-l-4 border-blue-500 p-3 mt-4 text-sm">
            <p className="font-semibold text-blue-900">Try this:</p>
            <ol className="text-blue-900 list-decimal list-inside mt-1 space-y-1">
              <li>Run "sonie headphones" with everything on — fuzzy catches the typo.</li>
              <li>Toggle <code>fuzzy</code> off and re-run — results degrade noticeably.</li>
              <li>Toggle <code>reranking</code> off — the Reranker step disappears from the panel and the Pipeline Quality Summary's Reranked stage drops out too.</li>
              <li>Toggle <code>llm</code> off — agent renders raw markdown product list with retrieval scores instead of a synthesized answer.</li>
            </ol>
          </div>

          <p className="text-xs text-gray-500">
            Toggles persist to <code>localStorage</code> via Zustand (<code>search-optimizations</code>) so they survive reloads. Reset with the <em>Reset</em> action on the Search Optimizations card.
          </p>
        </div>
      ),
    },
    {
      id: 'pipeline-summary',
      title: '📈 Pipeline Quality Summary',
      content: (
        <div className="space-y-4">
          <p className="text-sm text-gray-700">
            The last card in the Observability panel scores every retrieval against ESCI ground truth (when the query exists) or a self-referential confidence proxy (when it doesn't). It's how you tell — at a glance — whether each stage of the pipeline is earning its latency.
          </p>

          <h4 className="font-semibold text-gray-900 mt-2">Ground-truth layout</h4>
          <p className="text-sm text-gray-600">
            Three rows — <strong>BM25</strong>, <strong>Hybrid</strong>, <strong>Reranked</strong> — each with NDCG@10, MRR, Recall@20, Precision@10. ESCI labels are mapped to relevance:
          </p>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div className="bg-emerald-50 p-2 rounded text-center"><strong>E</strong>xact = 4.0</div>
            <div className="bg-blue-50 p-2 rounded text-center"><strong>S</strong>ubstitute = 1.0</div>
            <div className="bg-amber-50 p-2 rounded text-center"><strong>C</strong>omplement = 0.1</div>
            <div className="bg-gray-100 p-2 rounded text-center"><strong>I</strong>rrelevant = 0.0</div>
          </div>

          <h4 className="font-semibold text-gray-900 mt-2">Latency cost-benefit</h4>
          <p className="text-sm text-gray-600">
            A per-stage table with wall-clock latency and (for ground-truth queries) the marginal NDCG lift normalized to 100ms. Negative lift on the reranker row means it slowed you down without helping.
          </p>

          <h4 className="font-semibold text-gray-900 mt-2">Fallback layout</h4>
          <p className="text-sm text-gray-600">
            For novel queries (not in ESCI), the card shows a self-referential confidence proxy: top-1 reranker score, score gap to #2, score variance, and rank churn (top-10 positions that changed pre/post rerank). Color-coded high / medium / low chip — <em>not</em> NDCG, the card calls this out.
          </p>

          <div className="bg-amber-50 border-l-4 border-amber-500 p-3 mt-2 text-sm">
            <p className="font-semibold text-amber-900">Enable ground-truth metrics:</p>
            <p className="text-amber-900 mt-1">Ingest the ESCI judgments index once:</p>
            <pre className="bg-gray-900 text-gray-100 p-2 rounded text-xs overflow-x-auto mt-1">
              <code>cd langchain_agent{'\n'}PYTHONPATH=. python ingest_esci_judgments.py</code>
            </pre>
            <p className="text-amber-900 mt-1 text-xs">
              ~97k US queries / 1.8M judgments. After ingestion, queries that match an ESCI query exactly (lowercased) trigger the BM25 → Hybrid → Reranked layout.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'using-api',
      title: '🔌 Using the API',
      content: (
        <div className="space-y-4">
          <div className="space-y-3">
            <h4 className="font-semibold text-gray-900">REST Endpoint (Non-streaming)</h4>
            <pre className="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto">
              <code>{`POST /api/chat
Content-Type: application/json

{
  "message": "What are the best gaming laptops?",
  "thread_id": "my_session_123"
}

Response:
{
  "thread_id": "my_session_123",
  "response": "Here are some great gaming laptops...",
  "duration_ms": 2450.5,
  "citations": [
    {
      "label": "ASUS ROG Zephyrus G14",
      "url": "https://www.amazon.com/dp/B0B45M1KKP"
    }
  ]
}`}</code>
            </pre>

            <h4 className="font-semibold text-gray-900 mt-4">WebSocket Endpoint (Real-time Streaming)</h4>
            <pre className="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto">
              <code>{`ws://localhost:8000/ws/chat?thread_id=my_session_123

Client sends:
{"type": "chat_message", "message": "..."}

Server streams back:
{"type": "SearchProgressEvent", "node": "retriever", ...}
{"type": "OpenSearchQueryEvent", "query": {...}, ...}
{"type": "RerankerProgressEvent", ...}
{"type": "LLMResponseChunkEvent", "chunk": "Here are..."}
{"type": "AgentCompleteEvent", "response": "...", "citations": [...]}`}</code>
            </pre>
          </div>

          <div className="bg-amber-50 border-l-4 border-amber-500 p-3 mt-4">
            <p className="text-sm font-semibold text-amber-900">Use WebSocket for:</p>
            <ul className="text-sm text-amber-800 mt-1 space-y-1">
              <li>• Real-time responses and observability</li>
              <li>• Production applications needing streaming</li>
              <li>• Showing pipeline execution to users</li>
            </ul>
          </div>

          <div className="bg-blue-50 border-l-4 border-blue-500 p-3 mt-4">
            <p className="text-sm font-semibold text-blue-900">Use REST for:</p>
            <ul className="text-sm text-blue-800 mt-1 space-y-1">
              <li>• Simple integrations</li>
              <li>• Backend-to-backend calls</li>
              <li>• Simpler error handling</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'conversation-mgmt',
      title: '💾 Conversation Management',
      content: (
        <div className="space-y-4">
          <h4 className="font-semibold text-gray-900">REST Endpoints</h4>
          <div className="space-y-2 text-sm">
            <div className="border-l-4 border-blue-400 pl-3">
              <p className="font-mono text-blue-900">GET /api/conversations</p>
              <p className="text-gray-600">List all conversations (20 most recent by default)</p>
            </div>
            <div className="border-l-4 border-blue-400 pl-3">
              <p className="font-mono text-blue-900">GET /api/conversations/{'{thread_id}'}</p>
              <p className="text-gray-600">Get full message history for a conversation</p>
            </div>
            <div className="border-l-4 border-red-400 pl-3">
              <p className="font-mono text-red-900">DELETE /api/conversations/{'{thread_id}'}</p>
              <p className="text-gray-600">Delete a specific conversation</p>
            </div>
            <div className="border-l-4 border-red-400 pl-3">
              <p className="font-mono text-red-900">DELETE /api/conversations</p>
              <p className="text-gray-600">Delete ALL conversations (destructive!)</p>
            </div>
          </div>

          <h4 className="font-semibold text-gray-900 mt-4">Thread ID Format</h4>
          <p className="text-sm text-gray-600">
            Alphanumeric, underscore, hyphen, 1-64 chars. Auto-generated as <code className="bg-gray-100 px-1">conversation_{'<random>'}</code> if not provided.
          </p>
        </div>
      ),
    },
    {
      id: 'monitoring',
      title: '📊 Health & Monitoring',
      content: (
        <div className="space-y-4">
          <h4 className="font-semibold text-gray-900">Health Check Endpoints</h4>
          <div className="space-y-2 text-sm">
            <div className="bg-gray-50 p-3 rounded">
              <p className="font-mono text-gray-900">GET /api/health</p>
              <p className="text-gray-600 text-xs mt-1">Full health status of all dependencies (postgres, google_ai, vector_store)</p>
              <p className="text-gray-500 text-xs mt-1">Always returns 200, check status field for degraded</p>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <p className="font-mono text-gray-900">GET /api/health/ready</p>
              <p className="text-gray-600 text-xs mt-1">Kubernetes-style readiness probe (200 if ready, 503 if degraded)</p>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <p className="font-mono text-gray-900">GET /api/config</p>
              <p className="text-gray-600 text-xs mt-1">Runtime API URL discovery for frontend</p>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'examples',
      title: '💻 Example Queries',
      content: (
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="bg-blue-50 p-3 rounded">
              <p className="font-semibold text-blue-900">Product Search</p>
              <p className="text-sm text-blue-800">"What wireless earbuds have the best noise cancellation?"</p>
            </div>
            <div className="bg-green-50 p-3 rounded">
              <p className="font-semibold text-green-900">Comparison</p>
              <p className="text-sm text-green-800">"Compare iPhone 15 Pro vs Samsung Galaxy S24 Ultra"</p>
            </div>
            <div className="bg-purple-50 p-3 rounded">
              <p className="font-semibold text-purple-900">Attribute Filter</p>
              <p className="text-sm text-purple-800">"Show me red running shoes size 10"</p>
            </div>
            <div className="bg-orange-50 p-3 rounded">
              <p className="font-semibold text-orange-900">Follow-up</p>
              <p className="text-sm text-orange-800">User: "What are good gaming laptops?"<br/>Then: "Which one has the best battery life?"</p>
            </div>
            <div className="bg-pink-50 p-3 rounded">
              <p className="font-semibold text-pink-900">Brand-Specific</p>
              <p className="text-sm text-pink-800">"What Sony cameras are available?"</p>
            </div>
          </div>

          <div className="mt-4 bg-amber-50 border-l-4 border-amber-500 p-3">
            <p className="text-sm font-semibold text-amber-900">Note on Pricing</p>
            <p className="text-sm text-amber-800 mt-1">
              Products in this index do not include price data. Queries about price ranges (e.g. "under $100") will not filter by price.
              Focus on attributes like brand, color, size, features, and product categories.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'architecture',
      title: '🏗️ Architecture Overview',
      content: (
        <div className="space-y-4">
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-gray-900">Core Pipeline</p>
            <pre className="bg-gray-900 text-gray-100 p-2 rounded text-xs overflow-x-auto">
              <code>Intent Classifier → Query Evaluator → Retriever → Reranker → Quality Gate → LLM Agent</code>
            </pre>

            <p className="font-semibold text-gray-900 mt-3">Tech Stack</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">LLM</p>
                <p className="text-gray-600">Google Gemini 3 Flash</p>
              </div>
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">Embeddings</p>
                <p className="text-gray-600">Gemini Embedding 001 (768-dim)</p>
              </div>
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">Vector DB</p>
                <p className="text-gray-600">OpenSearch 2.19.1 (HNSW + BM25)</p>
              </div>
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">Checkpoints</p>
                <p className="text-gray-600">PostgreSQL 16</p>
              </div>
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">Framework</p>
                <p className="text-gray-600">LangGraph + LangChain</p>
              </div>
              <div className="bg-gray-50 p-2 rounded text-xs">
                <p className="font-mono text-gray-900">Frontend</p>
                <p className="text-gray-600">React 18 + TypeScript</p>
              </div>
            </div>

            <p className="font-semibold text-gray-900 mt-3">Data Flow</p>
            <ol className="list-decimal list-inside space-y-1 text-xs text-gray-700">
              <li>User question arrives via WebSocket or REST</li>
              <li>Intent classifier determines query type (search, comparison, etc.)</li>
              <li>Query evaluator calculates optimal hybrid search balance (alpha 0.0-1.0)</li>
              <li>Retriever fetches candidates from OpenSearch (vector + BM25 fusion)</li>
              <li>Reranker scores each result with LLM (0.0-1.0 relevance)</li>
              <li>Quality gate validates results, retries if score &lt; 0.5</li>
              <li>LLM agent generates conversational response with citations</li>
              <li>Entire thread saved to PostgreSQL checkpoints for resumption</li>
            </ol>
          </div>
        </div>
      ),
    },
    {
      id: 'troubleshooting',
      title: '🔧 Troubleshooting',
      content: (
        <div className="space-y-4">
          <div className="space-y-3 text-sm">
            <div className="border-l-4 border-red-500 pl-3">
              <p className="font-semibold text-gray-900">ModuleNotFoundError: No module named 'config'</p>
              <p className="text-gray-600">Missing <code className="bg-gray-100 px-1">PYTHONPATH=.</code></p>
              <p className="text-gray-500 text-xs mt-1">Fix: <code className="bg-gray-100 px-1">cd langchain_agent && PYTHONPATH=. pytest tests/</code></p>
            </div>

            <div className="border-l-4 border-red-500 pl-3">
              <p className="font-semibold text-gray-900">ConnectionError: Error connecting to OpenSearch</p>
              <p className="text-gray-600">OpenSearch not running</p>
              <p className="text-gray-500 text-xs mt-1">Fix: <code className="bg-gray-100 px-1">docker compose up -d</code> from repo root</p>
            </div>

            <div className="border-l-4 border-red-500 pl-3">
              <p className="font-semibold text-gray-900">Google AI API validation failed</p>
              <p className="text-gray-600">Missing GOOGLE_API_KEY</p>
              <p className="text-gray-500 text-xs mt-1">Fix: Get key from <a href="https://aistudio.google.com/apikey" className="text-blue-600 hover:underline">aistudio.google.com/apikey</a>, add to .env</p>
            </div>

            <div className="border-l-4 border-red-500 pl-3">
              <p className="font-semibold text-gray-900">WebSocket connection refused</p>
              <p className="text-gray-600">Backend not running</p>
              <p className="text-gray-500 text-xs mt-1">Fix: Start API with <code className="bg-gray-100 px-1">make dev-api</code></p>
            </div>

            <div className="border-l-4 border-yellow-500 pl-3">
              <p className="font-semibold text-gray-900">Results not relevant enough</p>
              <p className="text-gray-600">Try being more specific in your query</p>
              <p className="text-gray-500 text-xs mt-1">Good: "Sony WH-1000XM5" vs Bad: "good headphones"</p>
            </div>

            <div className="border-l-4 border-yellow-500 pl-3">
              <p className="font-semibold text-gray-900">Slow responses</p>
              <p className="text-gray-600">Check Observability panel for pipeline bottlenecks</p>
              <p className="text-gray-500 text-xs mt-1">Reranking typically takes longest; adjust RERANKER_TOP_K in .env</p>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'resources',
      title: '📚 Resources',
      content: (
        <div className="space-y-3 text-sm">
          <div className="space-y-2">
            <p className="font-semibold text-gray-900">Documentation</p>
            <ul className="space-y-1 text-gray-700">
              <li><a href="/docs" className="text-blue-600 hover:underline">📖 Interactive API Docs (Swagger UI)</a></li>
            </ul>

            <p className="font-semibold text-gray-900 mt-3">Configuration</p>
            <ul className="space-y-1 text-gray-700">
              <li><code className="bg-gray-100 px-1">langchain_agent/.env.example</code> - All environment variables</li>
              <li><code className="bg-gray-100 px-1">CLAUDE.md</code> - Detailed project guide</li>
            </ul>

            <p className="font-semibold text-gray-900 mt-3">Commands</p>
            <ul className="space-y-1 text-gray-600 font-mono text-xs">
              <li><code className="bg-gray-100 px-1">make dev</code> - Start all services</li>
              <li><code className="bg-gray-100 px-1">make dev-api</code> - Backend only</li>
              <li><code className="bg-gray-100 px-1">make dev-web</code> - Frontend only</li>
              <li><code className="bg-gray-100 px-1">make ci</code> - Local pre-push gate (black/isort/flake8/mypy/pytest)</li>
              <li><code className="bg-gray-100 px-1">PYTHONPATH=. pytest tests/</code> - Run tests</li>
              <li><code className="bg-gray-100 px-1">PYTHONPATH=. python ingest_esci_products.py</code> - Ingest products</li>
              <li><code className="bg-gray-100 px-1">PYTHONPATH=. python ingest_esci_judgments.py</code> - Ingest ground-truth judgments (enables NDCG/MRR/Recall@20)</li>
            </ul>
          </div>
        </div>
      ),
    },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">📖 Agentic Hybrid Search Guide</h1>
          <p className="text-gray-600">Complete guide to using the API, UI, and features</p>
        </div>

        {/* Table of Contents */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
          <h2 className="font-semibold text-gray-900 mb-3">Quick Navigation</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {sections.map((section) => (
              <button
                key={section.id}
                onClick={() => toggleSection(section.id)}
                className="text-left text-sm text-blue-600 hover:text-blue-700 hover:underline"
              >
                {section.title}
              </button>
            ))}
          </div>
        </div>

        {/* Sections */}
        <div className="space-y-4">
          {sections.map((section) => (
            <div key={section.id} className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <button
                onClick={() => toggleSection(section.id)}
                className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
              >
                <h2 className="text-lg font-semibold text-gray-900">{section.title}</h2>
                {expandedSections.has(section.id) ? (
                  <ChevronUp className="w-5 h-5 text-gray-500" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-gray-500" />
                )}
              </button>

              {expandedSections.has(section.id) && (
                <div className="border-t border-gray-200 p-4 bg-gray-50">{section.content}</div>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-600">
          <p>Need more help? Check the <a href="/docs" className="text-blue-600 hover:underline">API documentation</a></p>
        </div>
      </div>
    </div>
  )
}
