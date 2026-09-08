from __future__ import annotations

from pathlib import Path

import pytest

from cmpilot.pair_review import (
    PAIR_REVIEW_QUESTIONS,
    build_sealed_response,
    pair_review_form,
    validate_review_request,
)
from cmpilot.source_pairing import SourcePairingError
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


def _request() -> dict[str, str]:
    return {
        "target_id": DEVELOPMENT_IDS[0],
        "top_source_id": "src-example",
        "pair_hash": "a" * 64,
    }


def test_pair_review_form_is_fixed_all_yes() -> None:
    form = pair_review_form()
    assert set(form["questions"]) == {f"Q{number}" for number in range(1, 17)}
    assert form["decision_rule"] == "ACCEPT_IF_AND_ONLY_IF_ALL_16_ANSWERS_ARE_YES"
    assert form["rank_2_fallback"] is False


def test_sealed_request_accepts_only_lock_identity() -> None:
    validate_review_request(_request())
    with pytest.raises(SourcePairingError, match="fields changed"):
        validate_review_request({**_request(), "rankings": ["src-rank-2"]})
    with pytest.raises(PermissionError, match="development"):
        validate_review_request({**_request(), "target_id": "unseen"})


def test_sealed_response_is_accept_only_when_all_yes_and_has_no_advice() -> None:
    yes = {question: "YES" for question in PAIR_REVIEW_QUESTIONS}
    accepted = build_sealed_response(_request(), yes, {"packet": "b" * 64})
    assert accepted["decision"] == "ACCEPT"
    rejected_answers = dict(yes)
    rejected_answers["Q8"] = "NO"
    rejected = build_sealed_response(
        _request(), rejected_answers, {"packet": "b" * 64}
    )
    assert rejected["decision"] == "REJECT"
    assert set(rejected) == {"decision", "questions", "evidence_hashes", "pair_hash"}


def test_no_manual_fallback_cli_or_api_exists() -> None:
    module = (Path(__file__).resolve().parents[1] / "src/cmpilot/pair_review.py").read_text()
    assert "alternative_source_id" not in module
    assert "rank_2_source" not in module
