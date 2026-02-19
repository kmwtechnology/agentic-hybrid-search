"""
Agent state types for LangGraph custom agent.

Contains TypedDict definitions for the simplified agent state schema.

IMPORTANT: State fields may not be initialized. Always use state.get(key, default)
to access optional fields safely. Only 'messages' is guaranteed to exist.
"""

from typing import Sequence, List, Annotated, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langchain_core.documents import Document
from langgraph.graph import add_messages


class CustomAgentState(TypedDict, total=False):
    """
    State schema for custom agent graph with dynamic alpha.

    Uses a custom TypedDict instead of MessagesState to enable independent
    control of vector/full-text search weighting (alpha) based on query
    classification.

    Flow: intent_classifier → query_evaluator → retriever → reranker → quality_gate → agent

    IMPORTANT: Not all fields are guaranteed to exist at runtime.
    Use state.get(key, default) for safe access:
        - state.get("alpha", 0.25) instead of state["alpha"]
        - state.get("quality_gate_retried", False) instead of state["quality_gate_retried"]

    Required fields (always exist after first node):
        - messages: Conversation history

    Optional fields (may not exist until set by a node):
        - alpha, query_analysis, intent, summary_text
        - retrieved_documents, reranker_max_score
        - quality_gate_retried, quality_gate_reason
    """
    # Core message state (required - managed by add_messages reducer)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Intent classification state
    # Defaults: intent="question", intent_confidence=1.0
    intent: str
    intent_confidence: float  # 0.0-1.0, triggers clarify if < 0.7
    reasoning: str  # Explanation for classification
    user_query: str  # Extracted user query
    clarifying_questions: List[str]  # Questions to ask if confidence is low

    # Query evaluation state - alpha controls hybrid search balance
    # Defaults: alpha=0.25 (DEFAULT_ALPHA), query_analysis=""
    alpha: float
    query_analysis: str
    summary_text: Optional[str]

    # Retrieved documents from automatic retrieval
    # Default: empty list
    retrieved_documents: List[Document]

    # Reranker output
    reranker_max_score: float  # Max reranker score (0.0-1.0), set by reranker_node

    # Quality gate state (replaces alpha_refiner)
    # Defaults: quality_gate_retried=False
    quality_gate_retried: bool
    quality_gate_reason: Optional[str]
