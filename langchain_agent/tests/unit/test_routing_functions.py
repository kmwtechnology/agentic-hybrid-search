"""
Unit tests for EcommerceSearchAgent routing functions and llm_judge_node.

All LLM / DB / external dependencies are patched at construction time.
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Patch heavy init dependencies before importing EcommerceSearchAgent
_PATCH_TARGETS = [
    "main.LinkVerifier",
    "main.DocumentReplacer",
]


def _make_agent():
    """Return an EcommerceSearchAgent with external I/O bypassed."""
    with patch("main.LinkVerifier"), patch("main.DocumentReplacer"):
        from main import EcommerceSearchAgent

        agent = EcommerceSearchAgent.__new__(EcommerceSearchAgent)
        agent.llm = None
        agent.embeddings = None
        agent.vector_store = None
        agent.pool = None
        agent.async_pool = None
        agent.checkpointer = None
        agent.app = None
        agent.thread_id = None
        agent.emit_callback = None
        agent.event_loop = None
        agent.event_queue = []
        agent.retriever = None
        agent.reranker = None
        agent.alpha_estimator_llm = None
        agent.link_verifier = MagicMock()
        agent.doc_replacer = MagicMock()
        agent.judge = None
    return agent


# ---------------------------------------------------------------------------
# _route_after_intent
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteAfterIntent:
    def setup_method(self):
        self.agent = _make_agent()

    def test_clarify_intent_returns_clarify(self):
        state = {"intent": "clarify", "messages": []}
        assert self.agent._route_after_intent(state) == "clarify"

    def test_summary_intent_returns_summary(self):
        state = {"intent": "summary", "messages": []}
        assert self.agent._route_after_intent(state) == "summary"

    def test_search_intent_returns_other(self):
        state = {"intent": "search", "messages": []}
        assert self.agent._route_after_intent(state) == "other"

    def test_comparison_intent_returns_other(self):
        state = {"intent": "comparison", "messages": []}
        assert self.agent._route_after_intent(state) == "other"

    def test_attribute_filter_intent_returns_other(self):
        state = {"intent": "attribute_filter", "messages": []}
        assert self.agent._route_after_intent(state) == "other"

    def test_follow_up_intent_returns_other(self):
        state = {"intent": "follow_up", "messages": []}
        assert self.agent._route_after_intent(state) == "other"

    def test_missing_intent_defaults_to_other(self):
        # State with no intent key should default to "search" → "other"
        state = {"messages": []}
        assert self.agent._route_after_intent(state) == "other"


# ---------------------------------------------------------------------------
# _route_after_query_evaluator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteAfterQueryEvaluator:
    def setup_method(self):
        self.agent = _make_agent()

    def test_always_returns_retriever(self):
        for intent in ("search", "comparison", "attribute_filter", "follow_up", "summary"):
            state = {"intent": intent, "messages": []}
            assert self.agent._route_after_query_evaluator(state) == "retriever"


# ---------------------------------------------------------------------------
# _route_after_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteAfterSummary:
    def setup_method(self):
        self.agent = _make_agent()

    def test_summary_intent_returns_done(self):
        state = {"intent": "summary", "messages": []}
        assert self.agent._route_after_summary(state) == "done"

    def test_non_summary_intent_returns_continue(self):
        for intent in ("search", "comparison", "follow_up"):
            state = {"intent": intent, "messages": []}
            assert self.agent._route_after_summary(state) == "continue"

    def test_missing_intent_returns_continue(self):
        state = {"messages": []}
        assert self.agent._route_after_summary(state) == "continue"


# ---------------------------------------------------------------------------
# _quality_gate_route
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestQualityGateRoute:
    def setup_method(self):
        self.agent = _make_agent()

    def test_retry_triggered_and_retried_returns_retry(self):
        state = {
            "quality_gate_reason": "Retry triggered: low quality",
            "quality_gate_retried": True,
            "messages": [],
        }
        assert self.agent._quality_gate_route(state) == "retry"

    def test_retry_triggered_but_not_retried_returns_continue(self):
        state = {
            "quality_gate_reason": "Retry triggered: low quality",
            "quality_gate_retried": False,
            "messages": [],
        }
        assert self.agent._quality_gate_route(state) == "continue"

    def test_no_retry_in_reason_returns_continue(self):
        state = {
            "quality_gate_reason": "Quality acceptable",
            "quality_gate_retried": True,
            "messages": [],
        }
        assert self.agent._quality_gate_route(state) == "continue"

    def test_empty_reason_returns_continue(self):
        state = {"quality_gate_reason": "", "messages": []}
        assert self.agent._quality_gate_route(state) == "continue"

    def test_missing_reason_returns_continue(self):
        state = {"messages": []}
        assert self.agent._quality_gate_route(state) == "continue"


# ---------------------------------------------------------------------------
# llm_judge_node — skip conditions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmJudgeNodeSkips:
    def setup_method(self):
        self.agent = _make_agent()

    def _state_with(self, **kwargs):
        base = {"messages": [], "retrieved_documents": [MagicMock()]}
        base.update(kwargs)
        return base

    def test_skips_when_judge_off(self):
        state = self._state_with(optimizations={"llm": True, "llm_judge": False})
        result = self.agent.llm_judge_node(state)
        assert result["judgment"] is None
        assert result["judge_latency_ms"] == 0.0

    def test_skips_when_llm_off(self):
        state = self._state_with(optimizations={"llm": False, "llm_judge": True})
        result = self.agent.llm_judge_node(state)
        assert result["judgment"] is None

    def test_skips_when_intent_is_summary(self):
        state = self._state_with(
            optimizations={"llm": True, "llm_judge": True},
            intent="summary",
        )
        result = self.agent.llm_judge_node(state)
        assert result["judgment"] is None

    def test_skips_when_no_documents(self):
        state = {
            "messages": [],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "retrieved_documents": [],
        }
        result = self.agent.llm_judge_node(state)
        assert result["judgment"] is None

    def test_skips_when_no_ai_message(self):
        state = {
            "messages": [HumanMessage(content="find headphones")],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "retrieved_documents": [MagicMock()],
        }
        result = self.agent.llm_judge_node(state)
        assert result["judgment"] is None


# ---------------------------------------------------------------------------
# llm_judge_node — normal path (judge enabled, no hallucinations)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmJudgeNodeNormalPath:
    def setup_method(self):
        self.agent = _make_agent()

    def test_returns_judgment_on_success(self):
        from langchain_core.documents import Document

        mock_result = MagicMock()
        mock_result.verdict = "A_BETTER"
        mock_result.faithfulness = 0.95
        mock_result.hallucinations = []
        mock_result.model_dump.return_value = {"verdict": "A_BETTER", "faithfulness": 0.95}

        mock_judge = MagicMock()
        mock_judge.judge.return_value = mock_result
        self.agent.judge = mock_judge

        doc = Document(page_content="Sony WH-1000XM5 headphones", metadata={})
        state = {
            "messages": [AIMessage(content="Great headphones.")],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "user_query": "wireless headphones",
            "retrieved_documents": [doc],
        }

        with patch.object(self.agent, "_format_search_results", return_value="formatted"):
            result = self.agent.llm_judge_node(state)

        assert result["judgment"] == {"verdict": "A_BETTER", "faithfulness": 0.95}
        assert result["judge_latency_ms"] >= 0

    def test_returns_none_judgment_on_judge_exception(self):
        from langchain_core.documents import Document

        mock_judge = MagicMock()
        mock_judge.judge.side_effect = RuntimeError("API error")
        self.agent.judge = mock_judge

        doc = Document(page_content="content", metadata={})
        state = {
            "messages": [AIMessage(content="response")],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "user_query": "query",
            "retrieved_documents": [doc],
        }

        with patch.object(self.agent, "_format_search_results", return_value="formatted"):
            result = self.agent.llm_judge_node(state)

        assert result["judgment"] is None


# ---------------------------------------------------------------------------
# llm_judge_node — hallucination retry path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmJudgeNodeHallucinationRetry:
    def setup_method(self):
        self.agent = _make_agent()

    def test_retries_when_faithfulness_low_and_hallucinations_found(self):
        from langchain_core.documents import Document

        first_result = MagicMock()
        first_result.verdict = "B_BETTER"
        first_result.faithfulness = 0.60
        first_result.hallucinations = ["fake claim"]
        first_result.model_dump.return_value = {"faithfulness": 0.60}

        second_result = MagicMock()
        second_result.verdict = "A_BETTER"
        second_result.faithfulness = 0.92
        second_result.hallucinations = []
        second_result.model_dump.return_value = {"faithfulness": 0.92}

        mock_judge = MagicMock()
        mock_judge.judge.side_effect = [first_result, second_result]
        self.agent.judge = mock_judge

        doc = Document(page_content="content", metadata={})
        state = {
            "messages": [AIMessage(content="response with hallucination")],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "user_query": "query",
            "retrieved_documents": [doc],
            "hallucination_retry_used": False,
        }

        with (
            patch.object(self.agent, "_format_search_results", return_value="formatted"),
            patch.object(
                self.agent,
                "_regenerate_without_hallucinations",
                return_value="corrected response",
            ),
        ):
            result = self.agent.llm_judge_node(state)

        assert result["hallucination_retry_used"] is True
        assert result["corrected_response"] == "corrected response"
        assert result["judgment"]["faithfulness"] == 0.92

    def test_does_not_retry_when_retry_already_used(self):
        from langchain_core.documents import Document

        first_result = MagicMock()
        first_result.verdict = "B_BETTER"
        first_result.faithfulness = 0.60
        first_result.hallucinations = ["fake claim"]
        first_result.model_dump.return_value = {"faithfulness": 0.60}

        mock_judge = MagicMock()
        mock_judge.judge.return_value = first_result
        self.agent.judge = mock_judge

        doc = Document(page_content="content", metadata={})
        state = {
            "messages": [AIMessage(content="response")],
            "optimizations": {"llm": True, "llm_judge": True},
            "intent": "search",
            "user_query": "query",
            "retrieved_documents": [doc],
            "hallucination_retry_used": True,  # already retried
        }

        with patch.object(self.agent, "_format_search_results", return_value="formatted"):
            result = self.agent.llm_judge_node(state)

        # Should return first result without retrying
        assert result["judgment"]["faithfulness"] == 0.60
        assert "hallucination_retry_used" not in result
        assert mock_judge.judge.call_count == 1
