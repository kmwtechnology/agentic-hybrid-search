"""Schema-level tests for the categorical hallucination tier (issue #6).

Covers Pydantic validation of ``FlaggedClaim`` / ``HallucinationCategory``
and the legacy-string coercion path that lets older judge outputs continue
to validate.
"""

import pytest
from pydantic import ValidationError

from judge import (
    RETRY_ELIGIBLE_CATEGORIES,
    FlaggedClaim,
    HallucinationCategory,
    JudgmentResult,
)


@pytest.mark.unit
class TestFlaggedClaimValidation:
    def test_accepts_all_four_categories(self):
        for cat in (
            "fabrication",
            "cross_product_bleed",
            "inference",
            "overreach",
        ):
            fc = FlaggedClaim(claim="x", category=cat)
            assert fc.category.value == cat

    def test_rejects_unknown_category(self):
        with pytest.raises(ValidationError):
            FlaggedClaim(claim="x", category="speculation")

    def test_retry_eligible_set_is_exactly_the_dangerous_two(self):
        assert RETRY_ELIGIBLE_CATEGORIES == frozenset(
            {
                HallucinationCategory.fabrication,
                HallucinationCategory.cross_product_bleed,
            }
        )


@pytest.mark.unit
class TestJudgmentResultHallucinationsField:
    def _kwargs(self, hallucinations):
        return dict(
            verdict="tied",
            pairwise_justification="ok",
            faithfulness=0.9,
            answer_relevance=0.9,
            citation_accuracy=1.0,
            context_utilization=0.7,
            hallucinations=hallucinations,
        )

    def test_accepts_list_of_dicts(self):
        result = JudgmentResult(
            **self._kwargs(
                [
                    {
                        "claim": "Made in USA",
                        "category": "fabrication",
                        "reasoning": "no FACTS support",
                    },
                    {"claim": "best in class", "category": "overreach"},
                ]
            )
        )
        assert len(result.hallucinations) == 2
        assert result.hallucinations[0].category == HallucinationCategory.fabrication
        assert result.hallucinations[1].category == HallucinationCategory.overreach

    def test_legacy_list_of_strings_coerces_to_fabrication(self):
        result = JudgmentResult(**self._kwargs(["something fishy", "another"]))
        assert len(result.hallucinations) == 2
        for fc in result.hallucinations:
            assert fc.category == HallucinationCategory.fabrication

    def test_legacy_single_string_coerces(self):
        result = JudgmentResult(**self._kwargs("only one claim"))
        assert len(result.hallucinations) == 1
        assert result.hallucinations[0].claim == "only one claim"
        assert result.hallucinations[0].category == HallucinationCategory.fabrication

    def test_none_becomes_empty_list(self):
        result = JudgmentResult(**self._kwargs(None))
        assert result.hallucinations == []

    def test_empty_string_in_legacy_list_is_dropped(self):
        result = JudgmentResult(**self._kwargs(["", "real claim", "  "]))
        assert len(result.hallucinations) == 1
        assert result.hallucinations[0].claim == "real claim"

    def test_model_dump_round_trips_through_pydantic(self):
        original = JudgmentResult(
            **self._kwargs(
                [
                    {"claim": "x", "category": "inference", "reasoning": "para"},
                ]
            )
        )
        dumped = original.model_dump()
        # The dict form should be re-parseable (this is how the API surface
        # crosses the llm_judge_node → PipelineSummaryEvent boundary).
        round_tripped = JudgmentResult(**dumped)
        assert round_tripped.hallucinations[0].category == HallucinationCategory.inference
