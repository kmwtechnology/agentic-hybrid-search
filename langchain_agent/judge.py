"""
LLM-as-judge for Pipeline Quality Summary "Generation" stage.

Compares the agent's synthesized response (LLM:on path) against the
deterministic raw-product-list response (LLM:off path) and emits a
structured judgment with a pairwise verdict, four absolute scores
(faithfulness, answer_relevance, citation_accuracy, context_utilization),
a brief justification, and any specific hallucinations the judge spotted.

Bias mitigations:
  * Use a different model for the judge than the agent (we use
    gemini-3.1-flash-lite-preview by default; the agent uses
    gemini-3-flash-preview). Reduces self-preference.
  * Randomize "Response A" / "Response B" labels per call to mitigate
    positional bias on the pairwise verdict. The judge sees blind
    labels; we map back to llm/baseline server-side.
  * Tight token limits + temperature=0 for repeatability.

Cost: one extra Gemini Flash Lite call per judged query (~1-2s,
~$0.0005). Skipped when ``optimizations.llm_judge:false`` or
``optimizations.llm:false``.
"""

from __future__ import annotations

import logging
import random
import time
from typing import List, Literal, Optional

from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


Verdict = Literal["llm_better", "tied", "llm_worse"]


class JudgmentResult(BaseModel):
    """Structured output of one LLM-as-judge call."""

    verdict: Verdict = Field(description="Pairwise verdict: is the LLM response more useful?")
    pairwise_justification: str = Field(
        description="One or two sentences explaining the verdict.",
        max_length=500,
    )
    faithfulness: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.0-1.0. 1.0 means every factual claim in the LLM response is "
            "supported by the retrieved products. Lower for hallucinated facts."
        ),
    )
    answer_relevance: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0-1.0. How well the LLM response addresses the user query.",
    )
    citation_accuracy: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.0-1.0. If the response cites products, the citations match what the "
            "response says about them. 1.0 if no citations or all citations correct."
        ),
    )
    context_utilization: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.0-1.0. Fraction of the retrieved products that the LLM response "
            "meaningfully references."
        ),
    )
    hallucinations: List[str] = Field(
        default_factory=list,
        description=(
            "Specific claims in the LLM response NOT supported by the retrieved "
            "products. Empty list if no hallucinations found."
        ),
        max_length=10,
    )

    @field_validator("hallucinations", mode="before")
    @classmethod
    def _coerce_hallucinations(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return list(v)


_JUDGE_SYSTEM = (
    "You are an impartial evaluator of an e-commerce product-search assistant. "
    "You will judge how well a synthesized response addresses a user's query, "
    "compared to a deterministic raw-list response. Score strictly on the "
    "axes provided. Be specific about hallucinations — quote or paraphrase."
)


def _format_docs_for_prompt(documents: List[Document], max_chars: int = 360) -> str:
    """Compact numbered render of the retrieved docs, truncated for prompt size."""
    lines = []
    for i, doc in enumerate(documents, 1):
        title = doc.metadata.get("title") or "(untitled)"
        product_id = doc.metadata.get("product_id") or "?"
        snippet = (doc.page_content or "").replace("\n", " ").strip()
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip() + "…"
        lines.append(f"{i}. [{product_id}] {title}\n   {snippet}")
    return "\n".join(lines)


def _build_prompt(
    query: str,
    documents: List[Document],
    response_a: str,
    response_b: str,
    a_is_llm: bool,
) -> str:
    """Build the judge prompt with blind A/B labels."""
    docs_block = _format_docs_for_prompt(documents)
    llm_label = "Response A" if a_is_llm else "Response B"

    return f"""User query:
{query}

Retrieved products (top {len(documents)}):
{docs_block}

Response A:
{response_a}

Response B:
{response_b}

You are evaluating {llm_label} (the synthesized assistant response).
The other response is a deterministic raw-list rendering of the retrieved products.

Evaluate {llm_label} on these axes (each scored 0.0–1.0):
  • faithfulness: Every factual claim in {llm_label} is supported by the retrieved products. 1.0 = no unsupported claims; lower for hallucinations.
  • answer_relevance: How well {llm_label} addresses the user query intent.
  • citation_accuracy: If {llm_label} cites products, the citations match what it says about them. 1.0 if no citations or all are correct.
  • context_utilization: Proportion of retrieved products that {llm_label} meaningfully references.

Pairwise verdict — which response is more useful TO THIS USER for THIS query?
  • "llm_better": {llm_label} is meaningfully more useful (good synthesis, comparison, or recommendation justifies the prose form).
  • "tied": Both equally useful, or both poor.
  • "llm_worse": The raw-list response is more useful ({llm_label} added confusion, hallucination, or omitted relevant products).

List specific hallucinations: claims in {llm_label} that aren't supported by the retrieved products. Empty list if none.

Provide a 1-2 sentence justification for the pairwise verdict."""


class LLMJudge:
    """Pairwise + absolute LLM-as-judge for the Generation stage."""

    def __init__(self, model_name: str = "gemini-3.1-flash-lite-preview"):
        self.model_name = model_name
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            streaming=False,
            max_output_tokens=1024,
        )
        self.structured_llm = self.llm.with_structured_output(JudgmentResult)
        logger.info("LLMJudge loaded: model=%s", model_name)

    def judge(
        self,
        query: str,
        documents: List[Document],
        llm_response: str,
        baseline_response: str,
        *,
        seed: Optional[int] = None,
    ) -> JudgmentResult:
        """Score the LLM response against the baseline raw-list response.

        The verdict's polarity is normalized: "llm_better" always means the
        synthesized response wins, regardless of which blind label the model
        actually saw. We randomize A/B per call to mitigate positional bias.
        """
        rng = random.Random(seed) if seed is not None else random
        a_is_llm = rng.random() < 0.5
        response_a = llm_response if a_is_llm else baseline_response
        response_b = baseline_response if a_is_llm else llm_response

        prompt = _build_prompt(query, documents, response_a, response_b, a_is_llm)
        messages = [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        started = time.time()
        result: JudgmentResult = self.structured_llm.invoke(messages)
        elapsed = time.time() - started
        logger.info(
            "LLMJudge: verdict=%s in %.2fs (a_is_llm=%s)",
            result.verdict,
            elapsed,
            a_is_llm,
        )
        return result
