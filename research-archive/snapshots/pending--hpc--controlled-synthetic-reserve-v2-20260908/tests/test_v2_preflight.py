from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmpilot.v2_preflight import (
    TRAJECTORY_BUDGET_EXHAUSTED,
    V2ContextProfile,
    V2PreflightError,
    V2RuntimeLedger,
    bound_visible_tool_output,
    calculate_v2_turn_budget,
    classify_v2_technical_validity,
    preserve_raw_tool_output,
)


def test_exact_post_ingestion_budget_and_dynamic_generation_ceiling() -> None:
    profile = V2ContextProfile()
    first = calculate_v2_turn_budget(first_request_tokens=4_000, transcript_tokens=4_000, profile=profile)
    assert first.post_ingestion_tokens == 0
    assert first.available_trajectory_tokens == 16_384
    assert first.allowed_max_new_tokens == 4_096
    later = calculate_v2_turn_budget(first_request_tokens=4_000, transcript_tokens=19_000, profile=profile)
    assert later.post_ingestion_tokens == 15_000
    assert later.available_trajectory_tokens == 1_384
    assert later.allowed_max_new_tokens == 1_384


def test_trajectory_exhaustion_is_scientific_and_sends_no_request() -> None:
    budget = calculate_v2_turn_budget(first_request_tokens=2_000, transcript_tokens=18_384)
    assert budget.request_allowed is False
    assert budget.allowed_max_new_tokens == 0
    assert budget.termination_reason == TRAJECTORY_BUDGET_EXHAUSTED
    assert classify_v2_technical_validity(TRAJECTORY_BUDGET_EXHAUSTED) == "SCIENTIFIC"


def test_initial_feasibility_fails_closed() -> None:
    with pytest.raises(V2PreflightError, match=r"P \+ B \+ R"):
        calculate_v2_turn_budget(first_request_tokens=16_129, transcript_tokens=16_129)


def test_visible_output_preserves_head_tail_hash_and_exact_ceiling(tmp_path) -> None:
    raw = "α" * 40_000 + "THE-END"
    bounded = bound_visible_tool_output(raw)
    assert bounded.truncated is True
    assert bounded.visible_bytes <= 32 * 1024
    assert bounded.visible_text.startswith("α")
    assert bounded.visible_text.endswith("THE-END")
    assert bounded.raw_sha256 == hashlib.sha256(raw.encode()).hexdigest()
    path = tmp_path / "raw" / "0001.stdout"
    saved = preserve_raw_tool_output(path, raw)
    assert path.read_text() == raw
    assert saved == bounded
    with pytest.raises(V2PreflightError, match="refusing to overwrite"):
        preserve_raw_tool_output(path, raw)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("NO_TOOL_CALLS", "SCIENTIFIC"),
        ("MALFORMED_MODEL_TOOL_CALL", "SCIENTIFIC"),
        ("MODEL_CHOSEN_COMMAND_TIMEOUT", "SCIENTIFIC"),
        ("MAXIMUM_STEP_EXHAUSTION", "SCIENTIFIC"),
        ("CUDA_FAILURE", "TECHNICAL_INVALID"),
        ("TRANSPORT_FAILURE", "TECHNICAL_INVALID"),
        ("PARSER_DEFECT_VALID_SYNTAX", "TECHNICAL_INVALID"),
    ],
)
def test_v2_validity_policy(reason: str, expected: str) -> None:
    assert classify_v2_technical_validity(reason) == expected


class CharacterCounter:
    def count(self, messages: list[dict[str, str]]) -> int:
        return sum(len(item["role"]) + len(item["content"]) + 1 for item in messages)


def test_runtime_ledger_counts_full_visible_history_and_saves_raw_output(
    tmp_path: Path,
) -> None:
    initial = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "T"},
    ]
    ledger = V2RuntimeLedger(
        initial_messages=initial,
        counter=CharacterCounter(),
        raw_output_directory=tmp_path,
    )
    p = ledger.first_request_tokens
    ledger.append_message("assistant", "A" * 100)
    visible = ledger.append_tool_output("Z" * 40000)
    budget = ledger.next_turn_budget()
    assert visible.truncated is True
    assert (tmp_path / "tool-output-0001.txt").stat().st_size == 40000
    assert budget.transcript_tokens == CharacterCounter().count(ledger.messages)
    assert budget.post_ingestion_tokens == budget.transcript_tokens - p
    assert len(ledger.messages) == 4
