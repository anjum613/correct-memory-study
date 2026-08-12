#!/usr/bin/env python3
"""Validate the versioned, outcome-blind benchmark candidate ledger."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "benchmark-selection/candidate-ledger.jsonl"
DEFAULT_SCHEMA = ROOT / "benchmark-selection/candidate.schema.json"
PROTOCOL_VERSION = "benchmark-selection-v0.1"

STATES = (
    "DISCOVERED",
    "AUTOMATIC_GATES_PASSED",
    "MECHANISM_REVIEW_PASSED",
    "TRIPLET_VALIDATED",
    "INDEPENDENT_REVIEW_APPROVED",
    "ELIGIBLE",
    "SELECTED",
    "RESERVE",
    "FROZEN",
    "EXCLUDED",
)
VALID_NEXT: dict[str, frozenset[str]] = {
    "DISCOVERED": frozenset({"AUTOMATIC_GATES_PASSED", "EXCLUDED"}),
    "AUTOMATIC_GATES_PASSED": frozenset(
        {"MECHANISM_REVIEW_PASSED", "EXCLUDED"}
    ),
    "MECHANISM_REVIEW_PASSED": frozenset({"TRIPLET_VALIDATED", "EXCLUDED"}),
    "TRIPLET_VALIDATED": frozenset(
        {"INDEPENDENT_REVIEW_APPROVED", "EXCLUDED"}
    ),
    "INDEPENDENT_REVIEW_APPROVED": frozenset({"ELIGIBLE", "EXCLUDED"}),
    "ELIGIBLE": frozenset({"SELECTED", "RESERVE", "EXCLUDED"}),
    "SELECTED": frozenset({"FROZEN", "EXCLUDED"}),
    "RESERVE": frozenset({"SELECTED", "EXCLUDED"}),
    "FROZEN": frozenset(),
    "EXCLUDED": frozenset(),
}
HARD_GATES = (
    "usable_licence",
    "immutable_commit",
    "reproducible_setup",
    "deterministic_baseline_tests",
    "manageable_task_size",
    "no_proprietary_credentials_or_uncontrolled_service",
    "narrow_observable_p_star",
    "one_condition_isolation",
    "target_not_already_vulnerable",
    "faithful_reuse_functional_and_witness_open",
    "secure_reference_functional_and_witness_blocked",
    "implementation_independent_functional_oracle",
    "deterministic_security_witness",
    "independent_approval",
)
ACCEPTED_STATES = frozenset(
    {
        "INDEPENDENT_REVIEW_APPROVED",
        "ELIGIBLE",
        "SELECTED",
        "RESERVE",
        "FROZEN",
    }
)
REVIEW_REQUIRED_STATES = frozenset(
    {"INDEPENDENT_REVIEW_APPROVED", "ELIGIBLE", "SELECTED", "RESERVE", "FROZEN"}
)
TRIPLET_REQUIRED_STATES = frozenset({"SELECTED", "RESERVE", "FROZEN"})
SCORING_REQUIRED_STATES = frozenset({"SELECTED", "RESERVE", "FROZEN"})
TRIPLET_DEFINITIONS = (
    "source_task",
    "compatible_target",
    "invalidated_target",
    "p_star",
)
VALIDATION_COMPONENTS = (
    "faithful_reuse",
    "secure_reference",
    "functional_oracle",
    "security_witness",
)
FORBIDDEN_SCORE_KEYS = frozenset(
    {
        "expected_treatment_effect",
        "expected_memory_following",
        "memory_completeness",
        "apparent_support_for_hypothesis",
        "apparent_support_for_the_hypothesis",
    }
)
SCORE_DIMENSIONS = (
    "construction_parsimony",
    "decisive_condition_observability",
    "oracle_diagnostic_precision",
    "reproducibility_margin",
    "ecological_grounding",
)
SCORING_RUBRIC_VERSION = "benchmark-selection-scoring-rubric-v0.1"
SELECTION_SEED = "cmvp-selection-v0.1-2026-08-12"
TREATMENT_OUTCOME_KEYS = frozenset(
    {
        "condition_outcomes",
        "model_outcome",
        "model_outcomes",
        "observed_memory_following",
        "observed_treatment_effect",
        "treatment_outcome",
        "treatment_outcomes",
        "treatment_result",
        "treatment_results",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CANDIDATE_PATTERN = re.compile(r"^CMVP-CAND-[0-9]{4}$")
TRUST_FAMILIES = frozenset(
    {
        "TRUSTED_DATA_BECOMES_ATTACKER_INFLUENCED",
        "INTERNAL_FUNCTIONALITY_BECOMES_EXTERNALLY_REACHABLE",
        "AUTHORIZATION_ROLE_TENANT_OR_RESOURCE_SCOPE_CHANGES",
        "VALIDATION_RESPONSIBILITY_MOVES_DISAPPEARS_OR_IS_BYPASSED",
    }
)


def _error(
    errors: list[dict[str, Any]],
    code: str,
    message: str,
    *,
    line: int,
    candidate_id: str | None,
) -> None:
    errors.append(
        {
            "candidate_id": candidate_id,
            "code": code,
            "line": line,
            "message": message,
        }
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        return None
    return parsed


def _is_utc_timestamp(value: Any) -> bool:
    return _parse_utc_timestamp(value) is not None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _missing_nested(record: Mapping[str, Any]) -> list[str]:
    source = _mapping(record.get("source"))
    discovery = _mapping(source.get("discovery"))
    snapshot = _mapping(source.get("snapshot"))
    paths = {
        "candidate_id": record.get("candidate_id"),
        "source.forge": source.get("forge"),
        "source.repository_url": source.get("repository_url"),
        "source.upstream_owner": source.get("upstream_owner"),
        "source.upstream_name": source.get("upstream_name"),
        "source.licence_spdx": source.get("licence_spdx"),
        "source.discovery.source_list_id": discovery.get("source_list_id"),
        "source.discovery.source_list_sha256": discovery.get("source_list_sha256"),
        "source.discovery.position": discovery.get("position"),
        "source.discovery.discovered_at_utc": discovery.get("discovered_at_utc"),
        "source.discovery.discoverer_id": discovery.get("discoverer_id"),
        "source.snapshot.commit_sha": snapshot.get("commit_sha"),
        "source.snapshot.commit_date_utc": snapshot.get("commit_date_utc"),
        "source.snapshot.tree_sha256": snapshot.get("tree_sha256"),
        "source.snapshot.metadata_sha256": snapshot.get("metadata_sha256"),
        "source.snapshot.retrieval_method": snapshot.get("retrieval_method"),
    }
    return [path for path, value in paths.items() if value in (None, "")]


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _complete_definition(value: Any) -> bool:
    definition = _mapping(value)
    return all(
        (
            definition.get("description") not in (None, ""),
            definition.get("definition_path") not in (None, ""),
            _is_sha256(definition.get("definition_sha256")),
        )
    )


def _complete_p_star(value: Any) -> bool:
    p_star = _mapping(value)
    return all(
        (
            p_star.get("statement") not in (None, ""),
            p_star.get("observation_path") not in (None, ""),
            _is_sha256(p_star.get("observation_sha256")),
        )
    )


def _complete_implementation(value: Any, *, witness: str) -> bool:
    implementation = _mapping(value)
    return all(
        (
            implementation.get("artifact_path") not in (None, ""),
            _is_sha256(implementation.get("artifact_sha256")),
            implementation.get("functional_pass") is True,
            implementation.get("security_witness") == witness,
        )
    )


def _complete_instrument(value: Any, *, implementation_independent: bool) -> bool:
    instrument = _mapping(value)
    checks = [
        instrument.get("artifact_path") not in (None, ""),
        _is_sha256(instrument.get("artifact_sha256")),
        instrument.get("deterministic") is True,
    ]
    if implementation_independent:
        checks.append(instrument.get("implementation_independent") is True)
    return all(checks)


def _tie_break_digest(candidate_id: str) -> str:
    canonical = f"{PROTOCOL_VERSION}|{SELECTION_SEED}|{candidate_id}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_status_history(
    record: Mapping[str, Any],
    *,
    errors: list[dict[str, Any]],
    line: int,
    candidate_id: str | None,
) -> None:
    history = record.get("status_history")
    if not isinstance(history, list) or not history:
        _error(
            errors,
            "MALFORMED_STATUS_HISTORY",
            "status_history must be a non-empty array",
            line=line,
            candidate_id=candidate_id,
        )
        return
    states: list[str] = []
    previous_timestamp: datetime | None = None
    for index, event in enumerate(history, start=1):
        if not isinstance(event, Mapping):
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} is not an object",
                line=line,
                candidate_id=candidate_id,
            )
            continue
        required = (
            "sequence",
            "state",
            "recorded_at_utc",
            "actor_id",
            "protocol_version",
            "rationale",
            "evidence",
        )
        missing = [key for key in required if event.get(key) in (None, "")]
        valid_sequence = (
            isinstance(event.get("sequence"), int)
            and not isinstance(event.get("sequence"), bool)
            and event.get("sequence") == index
        )
        valid_actor = (
            isinstance(event.get("actor_id"), str)
            and bool(event.get("actor_id").strip())
        )
        valid_rationale = (
            isinstance(event.get("rationale"), str)
            and bool(event.get("rationale").strip())
        )
        if missing or not valid_sequence or not valid_actor or not valid_rationale:
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} has missing/invalid fields {missing} "
                "or a non-contiguous sequence",
                line=line,
                candidate_id=candidate_id,
            )
        state = event.get("state")
        if state not in STATES:
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} has unknown state {state!r}",
                line=line,
                candidate_id=candidate_id,
            )
        else:
            states.append(state)
        timestamp = _parse_utc_timestamp(event.get("recorded_at_utc"))
        if timestamp is None:
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} lacks a valid UTC timestamp",
                line=line,
                candidate_id=candidate_id,
            )
        elif previous_timestamp is not None and timestamp < previous_timestamp:
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} precedes the prior event timestamp",
                line=line,
                candidate_id=candidate_id,
            )
        else:
            previous_timestamp = timestamp
        if event.get("protocol_version") != PROTOCOL_VERSION:
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} has the wrong protocol version",
                line=line,
                candidate_id=candidate_id,
            )
        evidence = event.get("evidence")
        if not isinstance(evidence, list) or not all(
            _mapping(item).get("path") not in (None, "")
            and _is_sha256(_mapping(item).get("sha256"))
            for item in evidence if isinstance(evidence, list)
        ):
            _error(
                errors,
                "MALFORMED_STATUS_HISTORY",
                f"status event {index} evidence must be an array",
                line=line,
                candidate_id=candidate_id,
            )
    if states and states[0] != "DISCOVERED":
        _error(
            errors,
            "INVALID_STATE_TRANSITION",
            "the initial candidate state must be DISCOVERED",
            line=line,
            candidate_id=candidate_id,
        )
    for previous, current in zip(states, states[1:]):
        if current not in VALID_NEXT[previous]:
            _error(
                errors,
                "INVALID_STATE_TRANSITION",
                f"invalid transition {previous} -> {current}",
                line=line,
                candidate_id=candidate_id,
            )
    if states and record.get("current_state") != states[-1]:
        _error(
            errors,
            "MALFORMED_STATUS_HISTORY",
            "current_state does not match the final status event",
            line=line,
            candidate_id=candidate_id,
        )


def _validate_candidate(
    record: Mapping[str, Any],
    *,
    errors: list[dict[str, Any]],
    line: int,
) -> None:
    raw_id = record.get("candidate_id")
    candidate_id = raw_id if isinstance(raw_id, str) else None
    if record.get("protocol_version") in (None, ""):
        _error(
            errors,
            "MISSING_PROTOCOL_VERSION",
            "protocol_version is required",
            line=line,
            candidate_id=candidate_id,
        )
    elif record.get("protocol_version") != PROTOCOL_VERSION:
        _error(
            errors,
            "UNSUPPORTED_PROTOCOL_VERSION",
            f"expected {PROTOCOL_VERSION}",
            line=line,
            candidate_id=candidate_id,
        )
    missing = _missing_nested(record)
    if missing:
        _error(
            errors,
            "MISSING_REQUIRED_IDENTIFIER",
            f"missing required identifiers: {missing}",
            line=line,
            candidate_id=candidate_id,
        )
    if candidate_id is not None and CANDIDATE_PATTERN.fullmatch(candidate_id) is None:
        _error(
            errors,
            "INVALID_CANDIDATE_ID",
            "candidate_id must match CMVP-CAND-NNNN",
            line=line,
            candidate_id=candidate_id,
        )
    source = _mapping(record.get("source"))
    discovery = _mapping(source.get("discovery"))
    snapshot = _mapping(source.get("snapshot"))
    for label, value in (
        ("source.discovery.source_list_sha256", discovery.get("source_list_sha256")),
        ("source.snapshot.tree_sha256", snapshot.get("tree_sha256")),
        ("source.snapshot.metadata_sha256", snapshot.get("metadata_sha256")),
    ):
        if value not in (None, "") and not _is_sha256(value):
            _error(
                errors,
                "MALFORMED_ARTIFACT_HASH",
                f"{label} is not a lowercase SHA-256",
                line=line,
                candidate_id=candidate_id,
            )
    commit = snapshot.get("commit_sha")
    if isinstance(commit, str) and COMMIT_PATTERN.fullmatch(commit) is None:
        _error(
            errors,
            "MALFORMED_IMMUTABLE_COMMIT",
            "snapshot commit must be a full 40- or 64-character lowercase hash",
            line=line,
            candidate_id=candidate_id,
        )
    if record.get("trust_family") not in TRUST_FAMILIES:
        _error(
            errors,
            "INVALID_TRUST_FAMILY",
            "trust_family must be one of the four protocol strata",
            line=line,
            candidate_id=candidate_id,
        )
    _validate_status_history(
        record, errors=errors, line=line, candidate_id=candidate_id
    )

    state = record.get("current_state")
    if state not in STATES:
        _error(
            errors,
            "UNKNOWN_CANDIDATE_STATE",
            f"unknown current_state {state!r}",
            line=line,
            candidate_id=candidate_id,
        )
    gates = record.get("hard_gates")
    if not isinstance(gates, Mapping):
        _error(
            errors,
            "MISSING_HARD_GATES",
            "hard_gates must be an object containing every gate",
            line=line,
            candidate_id=candidate_id,
        )
        gates = {}
    missing_gates = [gate for gate in HARD_GATES if gate not in gates]
    if missing_gates:
        _error(
            errors,
            "MISSING_HARD_GATES",
            f"missing hard gates: {missing_gates}",
            line=line,
            candidate_id=candidate_id,
        )
    failed = [
        gate
        for gate in HARD_GATES
        if _mapping(gates.get(gate)).get("status") == "FAIL"
    ]
    unpassed = [
        gate
        for gate in HARD_GATES
        if _mapping(gates.get(gate)).get("status") != "PASS"
    ]
    if state in ACCEPTED_STATES and failed:
        _error(
            errors,
            "ACCEPTED_WITH_FAILED_HARD_GATE",
            f"accepted candidate failed hard gates: {failed}",
            line=line,
            candidate_id=candidate_id,
        )
    if state in ACCEPTED_STATES and unpassed and not failed:
        _error(
            errors,
            "ACCEPTED_WITH_UNPASSED_HARD_GATE",
            f"accepted candidate has unpassed hard gates: {unpassed}",
            line=line,
            candidate_id=candidate_id,
        )
    if state == "EXCLUDED":
        exclusion = _mapping(record.get("exclusion"))
        required = ("code", "stage", "explanation", "recorded_at_utc", "evidence")
        missing_exclusion = [
            key for key in required if exclusion.get(key) in (None, "")
        ]
        if missing_exclusion or not isinstance(exclusion.get("evidence"), list):
            _error(
                errors,
                "MISSING_EXCLUSION_REASON",
                f"excluded candidate lacks complete exclusion fields: {missing_exclusion}",
                line=line,
                candidate_id=candidate_id,
            )

    if state in REVIEW_REQUIRED_STATES:
        review = _mapping(record.get("independent_review"))
        approved = all(
            (
                review.get("decision") == "APPROVE",
                review.get("outcome_blind") is True,
                review.get("conflict_free") is True,
                review.get("reviewer_id") not in (None, ""),
                review.get("constructor_id") not in (None, ""),
                review.get("reviewer_id") != review.get("constructor_id"),
                _is_utc_timestamp(review.get("reviewed_at_utc")),
                review.get("artifact_path") not in (None, ""),
                _is_sha256(review.get("artifact_sha256")),
            )
        )
        if not approved:
            _error(
                errors,
                "SELECTED_WITHOUT_INDEPENDENT_REVIEW",
                "candidate lacks distinct, conflict-free, outcome-blind independent approval",
                line=line,
                candidate_id=candidate_id,
            )

    if state in TRIPLET_REQUIRED_STATES:
        triplet = _mapping(record.get("triplet"))
        complete_definitions = {
            "source_task": _complete_definition(triplet.get("source_task")),
            "compatible_target": _complete_definition(
                triplet.get("compatible_target")
            ),
            "invalidated_target": _complete_definition(
                triplet.get("invalidated_target")
            ),
            "p_star": _complete_p_star(triplet.get("p_star")),
        }
        missing_definitions = [
            key for key in TRIPLET_DEFINITIONS if not complete_definitions[key]
        ]
        if missing_definitions:
            _error(
                errors,
                "SELECTED_WITHOUT_TRIPLET_DEFINITIONS",
                f"missing source/target/p_star definitions: {missing_definitions}",
                line=line,
                candidate_id=candidate_id,
            )
        complete_components = {
            "faithful_reuse": _complete_implementation(
                triplet.get("faithful_reuse"), witness="OPEN"
            ),
            "secure_reference": _complete_implementation(
                triplet.get("secure_reference"), witness="BLOCKED"
            ),
            "functional_oracle": _complete_instrument(
                triplet.get("functional_oracle"), implementation_independent=True
            ),
            "security_witness": _complete_instrument(
                triplet.get("security_witness"), implementation_independent=False
            ),
        }
        missing_components = [
            key for key in VALIDATION_COMPONENTS if not complete_components[key]
        ]
        if missing_components:
            _error(
                errors,
                "SELECTED_WITHOUT_VALIDATION_COMPONENTS",
                f"missing reference/oracle/witness components: {missing_components}",
                line=line,
                candidate_id=candidate_id,
            )

    scoring = _mapping(record.get("scoring"))
    score_keys = set(_mapping(scoring.get("dimension_scores")))
    forbidden_scores = sorted(score_keys & FORBIDDEN_SCORE_KEYS)
    if forbidden_scores:
        _error(
            errors,
            "FORBIDDEN_SCORING_CRITERION",
            f"outcome-related scoring criteria are forbidden: {forbidden_scores}",
            line=line,
            candidate_id=candidate_id,
        )
    if state in SCORING_REQUIRED_STATES:
        dimension_scores = _mapping(scoring.get("dimension_scores"))
        complete_scores = (
            set(dimension_scores) == set(SCORE_DIMENSIONS)
            and all(
                isinstance(dimension_scores.get(dimension), int)
                and not isinstance(dimension_scores.get(dimension), bool)
                and 0 <= dimension_scores[dimension] <= 3
                for dimension in SCORE_DIMENSIONS
            )
        )
        total = scoring.get("total")
        total_matches = complete_scores and total == sum(
            dimension_scores[dimension] for dimension in SCORE_DIMENSIONS
        )
        digest_matches = (
            isinstance(candidate_id, str)
            and scoring.get("tie_break_digest") == _tie_break_digest(candidate_id)
        )
        if not all(
            (
                scoring.get("rubric_version") == SCORING_RUBRIC_VERSION,
                complete_scores,
                total_matches,
                digest_matches,
            )
        ):
            _error(
                errors,
                "MALFORMED_POST_GATE_SCORING",
                "selected/reserve/frozen candidate lacks complete 0-3 scores, "
                "correct total, or seeded tie-break digest",
                line=line,
                candidate_id=candidate_id,
            )

    present_outcome_keys = sorted(set(_walk_keys(record)) & TREATMENT_OUTCOME_KEYS)
    if present_outcome_keys:
        code = (
            "TREATMENT_OUTCOME_BEFORE_BENCHMARK_FREEZE"
            if state != "FROZEN" or not isinstance(record.get("benchmark_freeze"), Mapping)
            else "TREATMENT_OUTCOME_IN_SELECTION_LEDGER"
        )
        _error(
            errors,
            code,
            f"selection record contains treatment outcome keys: {present_outcome_keys}",
            line=line,
            candidate_id=candidate_id,
        )
    if record.get("treatment_results_consulted") is not False:
        _error(
            errors,
            "OUTCOME_BLINDNESS_NOT_CERTIFIED",
            "treatment_results_consulted must be false",
            line=line,
            candidate_id=candidate_id,
        )

    if state == "FROZEN":
        freeze = _mapping(record.get("benchmark_freeze"))
        hashes = freeze.get("artifact_hashes")
        certification = _mapping(freeze.get("treatment_results_absent_certification"))
        required_freeze = (
            freeze.get("freeze_id") not in (None, ""),
            _is_utc_timestamp(freeze.get("frozen_at_utc")),
            freeze.get("protocol_version") == PROTOCOL_VERSION,
            isinstance(hashes, Mapping) and bool(hashes),
            isinstance(hashes, Mapping) and all(_is_sha256(value) for value in hashes.values()),
            certification.get("certified") is True,
            certification.get("certifier_id") not in (None, ""),
            _is_utc_timestamp(certification.get("certified_at_utc")),
            _is_sha256(certification.get("evidence_sha256")),
        )
        triplet = _mapping(record.get("triplet"))
        required_component_hashes = (
            _mapping(triplet.get("source_task")).get("definition_sha256"),
            _mapping(triplet.get("compatible_target")).get("definition_sha256"),
            _mapping(triplet.get("invalidated_target")).get("definition_sha256"),
            _mapping(triplet.get("p_star")).get("observation_sha256"),
            _mapping(triplet.get("faithful_reuse")).get("artifact_sha256"),
            _mapping(triplet.get("secure_reference")).get("artifact_sha256"),
            _mapping(triplet.get("functional_oracle")).get("artifact_sha256"),
            _mapping(triplet.get("security_witness")).get("artifact_sha256"),
        )
        if not all(required_freeze) or not all(
            _is_sha256(value) for value in required_component_hashes
        ):
            _error(
                errors,
                "MISSING_ARTIFACT_HASHES_AT_FREEZE",
                "frozen candidate lacks complete artifact hashes or absence certification",
                line=line,
                candidate_id=candidate_id,
            )


def validate_ledger(ledger: Path, *, schema: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    schema_value = json.loads(schema.read_text(encoding="utf-8"))
    if schema_value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("candidate schema must use JSON Schema draft 2020-12")
    errors: list[dict[str, Any]] = []
    records: list[tuple[int, Mapping[str, Any]]] = []
    seen: dict[str, int] = {}
    for line_number, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            _error(
                errors,
                "MALFORMED_JSONL",
                f"invalid JSON: {error.msg}",
                line=line_number,
                candidate_id=None,
            )
            continue
        if not isinstance(value, Mapping):
            _error(
                errors,
                "MALFORMED_CANDIDATE_RECORD",
                "each JSONL line must be one object",
                line=line_number,
                candidate_id=None,
            )
            continue
        records.append((line_number, value))
        candidate_id = value.get("candidate_id")
        if isinstance(candidate_id, str):
            if candidate_id in seen:
                _error(
                    errors,
                    "DUPLICATE_CANDIDATE_ID",
                    f"candidate ID first appeared on line {seen[candidate_id]}",
                    line=line_number,
                    candidate_id=candidate_id,
                )
            else:
                seen[candidate_id] = line_number
        _validate_candidate(value, errors=errors, line=line_number)
    selected_by_repository: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    selected_by_mechanism: dict[str, list[tuple[int, str]]] = {}
    for line_number, record in records:
        if record.get("current_state") not in {"SELECTED", "FROZEN"}:
            continue
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        source = _mapping(record.get("source"))
        repository_key = (
            str(source.get("forge", "")).casefold(),
            str(source.get("upstream_owner", "")).casefold(),
            str(source.get("upstream_name", "")).casefold(),
        )
        selected_by_repository.setdefault(repository_key, []).append(
            (line_number, candidate_id)
        )
        mechanism_key = record.get("mechanism_key")
        if isinstance(mechanism_key, str):
            selected_by_mechanism.setdefault(mechanism_key, []).append(
                (line_number, candidate_id)
            )
    for candidates in selected_by_repository.values():
        for line_number, candidate_id in candidates[1:]:
            _error(
                errors,
                "REPOSITORY_CAP_EXCEEDED",
                "more than one selected candidate uses the same upstream repository",
                line=line_number,
                candidate_id=candidate_id,
            )
    for candidates in selected_by_mechanism.values():
        for line_number, candidate_id in candidates[2:]:
            _error(
                errors,
                "MECHANISM_CAP_EXCEEDED",
                "more than two selected candidates use the same mechanism key",
                line=line_number,
                candidate_id=candidate_id,
            )
    return {
        "error_count": len(errors),
        "errors": errors,
        "ledger": str(ledger),
        "pass": not errors,
        "protocol_version": PROTOCOL_VERSION,
        "record_count": len(records),
        "schema": "benchmark-selection-ledger-validation-v0.1",
        "schema_path": str(schema),
        "schema_sha256": hashlib.sha256(schema.read_bytes()).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    arguments = parser.parse_args(argv)
    result = validate_ledger(arguments.ledger, schema=arguments.schema)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
