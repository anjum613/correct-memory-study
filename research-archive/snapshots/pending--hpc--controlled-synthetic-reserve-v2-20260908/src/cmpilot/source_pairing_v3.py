"""Generic B-only top-one matching and irrelevant controls for V3."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from cmpilot.memory_lifecycle import memory_metrics, render_memory_packet
from cmpilot.source_pairing import (
    SourcePairingError,
    stable_record_hash,
    token_shingles,
    validate_b_only_mapping,
)
from cmpilot.source_pairing_v2 import (
    MEANINGFUL_RANKING_DIMENSIONS,
    score_candidate_v2,
)
from cmpilot.source_validation import (
    corpus_manifest_hash,
    validate_source_correct_entry,
    validate_timestamp,
)
from cmpilot.target_identity_v3 import TargetIdentityScope


MATCHER_SCHEMA_V3 = "cmpilot-b-only-lexicographic-matcher-v3"
PAIR_LOCK_SCHEMA_V3 = "cmpilot-source-pair-lock-v3"
IRRELEVANT_SCHEMA_V3 = "cmpilot-irrelevant-memory-selection-v3"
IRRELEVANT_LOCK_SCHEMA_V3 = "cmpilot-irrelevant-memory-lock-v3"
HARD_GATES_V3 = (
    "FROZEN_CORPUS_MEMBERSHIP_AND_HASH",
    "LANGUAGE_EXACT_PYTHON",
    "COARSE_TIMESTAMP_DATE",
    "REAL_RECONSTRUCTIBLE_SOURCE_BUILD_PASS",
    "SOURCE_TASK_TEST_PASS_AND_PROVENANCE",
    "NONEMPTY_CONTROLLED_OPERATION_CLASS_INTERSECTION",
    "REQUIRED_LIBRARY_API_MATCH_WHEN_MARKED_REQUIRED",
)
LEXICOGRAPHIC_RANKING_V3 = (
    "PRIMARY_OPERATION_CLASS_EXACT_DESC",
    "OPERATION_CLASS_INTERSECTION_COUNT_DESC",
    "SAME_REQUIRED_OR_PUBLIC_LIBRARY_API_DESC",
    "ORDERED_API_SEQUENCE_LCS_DESC",
    "TYPE_DATA_ROLE_MULTISET_JACCARD_DESC",
    "NORMALIZED_AST_MULTISET_JACCARD_DESC",
    "TOKEN_5_SHINGLE_JACCARD_DESC",
    "HASH_VECTORIZER_TASK_COSINE_DESC",
    "SOURCE_TIER_S1_S2_S3_ASC",
    "CANONICAL_SOURCE_IDENTITY_SHA256_ASC",
)
IRRELEVANT_HARD_GATES_V3 = (
    "REAL_SOURCE",
    "SOURCE_CORRECT",
    "SOURCE_SIDE_A_OR_B_SAFETY_EVIDENCE",
    "SAME_LANGUAGE",
    "SAME_PACKET_TEMPLATE",
    "COARSE_TIMESTAMP_DATE",
    "NO_OPERATION_CLASS_INTERSECTION",
    "NO_TARGET_API_OR_SYMBOL_LEAKAGE",
    "NOT_RELEVANT_SOURCE_OR_EXACT_DUPLICATE",
)
IRRELEVANT_SELECTION_V3 = (
    "ABS_PACKET_LEXICAL_TOKEN_DIFFERENCE_ASC",
    "ABS_IMPLEMENTATION_BYTE_DIFFERENCE_ASC",
    "ABS_VALIDATION_EVIDENCE_BYTE_DIFFERENCE_ASC",
    "SOURCE_TIER_ASC",
    "CANONICAL_SOURCE_IDENTITY_SHA256_ASC",
)
_OPERATION_ALIASES = {"AUTHENTICATION_AUTHORIZATION": "AUTHENTICATION_FLOW"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXPLICIT_DOTTED_API = re.compile(
    r"`((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)`"
)
_TOKEN_BINS = (0, 256, 512, 1024, 2048, 4096, 8192, 16384)
_GENERIC_TARGET_SYMBOLS = frozenset(
    {
        "admin",
        "class",
        "content",
        "converter",
        "core",
        "data",
        "false",
        "from",
        "href",
        "html",
        "identity",
        "import",
        "init",
        "link",
        "none",
        "page",
        "path",
        "props",
        "request",
        "response",
        "self",
        "true",
        "type",
        "update",
        "url",
    }
)


class SourcePairingV3Error(SourcePairingError):
    """A V3 generic matching or control invariant failed."""


def _iso_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SourcePairingV3Error("target B date must be YYYY-MM-DD UTC metadata")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SourcePairingV3Error("target B date is invalid") from error


def _source_date(entry: Mapping[str, Any]) -> date:
    try:
        parsed = datetime.fromisoformat(str(entry["commit_timestamp"]))
    except (KeyError, ValueError) as error:
        raise SourcePairingV3Error("source timestamp is absent or invalid") from error
    if parsed.tzinfo is None:
        raise SourcePairingV3Error("source timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).date()


def _operations(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(_OPERATION_ALIASES.get(str(value), str(value)) for value in values)


def _tier(entry: Mapping[str, Any], target_id: str) -> str:
    tiers = entry.get("source_tier_by_target")
    if not isinstance(tiers, Mapping) or target_id not in tiers:
        raise SourcePairingV3Error("source tier is absent for supplied target")
    value = str(tiers[target_id])
    if value not in {"S1", "S2", "S3"}:
        raise SourcePairingV3Error("source tier is invalid")
    return value


def _tier_number(value: str) -> int:
    if value not in {"S1", "S2", "S3"}:
        raise SourcePairingV3Error("source tier is invalid")
    return int(value[1])


def _identity_hash(entry: Mapping[str, Any]) -> str:
    value = entry.get("candidate_identity_sha256")
    if isinstance(value, str) and _SHA256.fullmatch(value):
        return value
    return stable_record_hash(
        {
            "source_id": entry.get("source_id"),
            "repository_url": entry.get("repository_url"),
            "repository_commit": entry.get("repository_commit"),
            "source_file": entry.get("source_file"),
            "source_symbol": entry.get("source_symbol"),
            "implementation_sha256": hashlib.sha256(
                str(entry.get("source_implementation_or_patch", "")).encode("utf-8")
            ).hexdigest(),
            "source_task_sha256": hashlib.sha256(
                str(entry.get("source_task_description", "")).encode("utf-8")
            ).hexdigest(),
        }
    )


def _rank_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    scores = row["scores"]
    return (
        -int(bool(scores["primary_operation_class_exact"])),
        -int(scores["operation_class_intersection_count"]),
        -int(bool(scores["same_required_or_public_library_api"])),
        -float(scores["api_sequence_similarity"]),
        -float(scores["type_data_role_similarity"]),
        -float(scores["ast_similarity"]),
        -float(scores["token_similarity"]),
        -float(scores["semantic_similarity"]),
        _tier_number(str(row["source_tier"])),
        str(row["source_identity_sha256"]),
    )


def _meaningful_vector(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row["scores"][name] for name in MEANINGFUL_RANKING_DIMENSIONS)


def _scientific_equivalence_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    """Resolve exact ties without consulting any historical p-star annotation."""

    return (
        _operations(entry.get("operation_class", ())),
        tuple(str(item) for item in entry.get("API_sequence", ())),
        tuple(str(item) for item in entry.get("type_or_data_role_signature", ())),
        hashlib.sha256(
            str(entry.get("source_implementation_or_patch", "")).encode("utf-8")
        ).hexdigest(),
        hashlib.sha256(
            str(entry.get("source_task_description", "")).encode("utf-8")
        ).hexdigest(),
    )


def matcher_design_record_v3() -> dict[str, Any]:
    return {
        "schema": MATCHER_SCHEMA_V3,
        "b_only": True,
        "hard_gates": list(HARD_GATES_V3),
        "ranking": list(LEXICOGRAPHIC_RANKING_V3),
        "meaningful_dimensions": list(MEANINGFUL_RANKING_DIMENSIONS),
        "global_similarity_threshold": None,
        "combined_or_weighted_score": None,
        "top_one": True,
        "rank_2_fallback": False,
        "manual_fallback": False,
        "pre_lock_focal_safety_annotation_used": False,
        "target_oracle_features": [],
    }


def rank_sources_v3(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
    scope: TargetIdentityScope,
) -> list[dict[str, Any]]:
    validate_b_only_mapping(target, target_identity_validator=scope.validate)
    target_id = str(target["benchmark_instance_id"])
    target_date = _iso_date(target_b_date_utc)
    if not entries:
        raise SourcePairingV3Error("source corpus cannot be empty")
    prepared_hash = corpus_manifest_hash(entries)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        source_id = str(entry.get("source_id", ""))
        if not source_id or source_id in seen:
            raise SourcePairingV3Error("source IDs must be nonempty and unique")
        seen.add(source_id)
        reasons: list[str] = []
        try:
            validate_source_correct_entry(entry, target_id=target_id)
        except SourcePairingError as error:
            reasons.append(f"SOURCE_CORRECT:{type(error).__name__}")
        scores = score_candidate_v2(target, entry)
        if not scores["language_exact"]:
            reasons.append("LANGUAGE_INCOMPATIBLE")
        try:
            if _source_date(entry) > target_date:
                reasons.append("COARSE_TIMESTAMP_INELIGIBLE")
        except SourcePairingV3Error:
            reasons.append("COARSE_TIMESTAMP_INVALID")
        if int(scores["operation_class_intersection_count"]) < 1:
            reasons.append("OPERATION_CLASS_INCOMPATIBLE")
        if not scores["required_api_match"]:
            reasons.append("REQUIRED_API_INCOMPATIBLE")
        rows.append(
            {
                "source_id": source_id,
                "source_entry_sha256": stable_record_hash(entry),
                "source_identity_sha256": _identity_hash(entry),
                "source_tier": _tier(entry, target_id),
                "hard_gate_pass": not reasons,
                "hard_gate_reasons": reasons,
                "scores": scores,
                "global_or_weighted_score": None,
                "source_correct_pre_lock": "SOURCE_CORRECT" not in " ".join(reasons),
                "focal_safety_evaluated_pre_lock": False,
                "prepared_corpus_sha256": prepared_hash,
            }
        )
    rows.sort(key=lambda row: (not row["hard_gate_pass"], _rank_key(row)))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


def _resolve_top_ambiguity(
    top: Mapping[str, Any],
    runner_up: Mapping[str, Any],
    entries_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if _meaningful_vector(top) != _meaningful_vector(runner_up):
        return {"status": "UNAMBIGUOUS_FIRST_MEANINGFUL_DIFFERENCE", "hash_tiebreak_used": False}
    top_key = _scientific_equivalence_key(entries_by_id[str(top["source_id"])])
    runner_key = _scientific_equivalence_key(entries_by_id[str(runner_up["source_id"])])
    if top_key != runner_key:
        raise SourcePairingV3Error("MATCH_AMBIGUOUS_SUBSTANTIVE_TIE")
    return {"status": "EQUIVALENT_EPISODE_HASH_TIEBREAK", "hash_tiebreak_used": True}


def select_top_source_v3(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
    scope: TargetIdentityScope,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rankings = rank_sources_v3(
        target, entries, target_b_date_utc=target_b_date_utc, scope=scope
    )
    eligible = [row for row in rankings if row["hard_gate_pass"]]
    if not eligible:
        raise SourcePairingV3Error("NO_SOURCE_PASSES_SOURCE_CORRECT_HARD_GATES")
    entries_by_id = {str(entry["source_id"]): entry for entry in entries}
    ambiguity = (
        {"status": "SINGLE_ELIGIBLE_SOURCE", "hash_tiebreak_used": False}
        if len(eligible) == 1
        else _resolve_top_ambiguity(eligible[0], eligible[1], entries_by_id)
    )
    design = matcher_design_record_v3()
    lock_body = {
        "schema": PAIR_LOCK_SCHEMA_V3,
        "target_id": target["benchmark_instance_id"],
        "target_scope_purpose": scope.purpose,
        "target_identity_list_sha256": scope.identity_list_sha256,
        "top_source_id": eligible[0]["source_id"],
        "top_source_entry_sha256": eligible[0]["source_entry_sha256"],
        "target_representation_sha256": stable_record_hash(target),
        "target_b_date_utc": target_b_date_utc,
        "prepared_source_corpus_sha256": corpus_manifest_hash(entries),
        "matcher_design_sha256": stable_record_hash(design),
        "full_rankings_sha256": stable_record_hash(rankings),
        "ambiguity": ambiguity,
        "top_one": True,
        "rank_2_fallback": False,
        "focal_safety_evaluated_pre_lock": False,
    }
    return rankings, {**lock_body, "pair_hash": stable_record_hash(lock_body)}


def enforce_top_source_lock_v3(
    lock: Mapping[str, Any], requested_source_id: str
) -> None:
    if lock.get("schema") != PAIR_LOCK_SCHEMA_V3:
        raise SourcePairingV3Error("V3 pair lock schema mismatch")
    if requested_source_id != lock.get("top_source_id"):
        raise PermissionError("rank-2/manual source fallback is forbidden")
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise SourcePairingV3Error("top-one lock policy changed")
    if lock.get("focal_safety_evaluated_pre_lock") is not False:
        raise SourcePairingV3Error("pre-lock focal-safety matcher gate was introduced")
    body = {key: value for key, value in lock.items() if key != "pair_hash"}
    if stable_record_hash(body) != lock.get("pair_hash"):
        raise SourcePairingV3Error("V3 pair lock hash mismatch")


def validate_locked_source_timestamp_v3(
    lock: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_timestamp_epoch: int,
) -> dict[str, Any]:
    source_id = str(lock.get("top_source_id", ""))
    enforce_top_source_lock_v3(lock, source_id)
    matches = [entry for entry in entries if entry.get("source_id") == source_id]
    if len(matches) != 1:
        raise SourcePairingV3Error("locked source does not resolve uniquely")
    status = "PASS"
    try:
        validate_timestamp(matches[0].get("commit_timestamp_epoch"), target_b_timestamp_epoch)
    except SourcePairingError:
        status = "REJECT_POSTDATED_NO_FALLBACK"
    return {
        "schema": "cmpilot-sealed-exact-timestamp-validation-v3",
        "lock_kind": "PAIR_TOP_ONE_V3",
        "lock_sha256": stable_record_hash(lock),
        "source_id": source_id,
        "source_timestamp_epoch": matches[0].get("commit_timestamp_epoch"),
        "target_b_timestamp_epoch": target_b_timestamp_epoch,
        "status": status,
        "fallback_attempted": False,
    }


def _required_api_families(target: Mapping[str, Any]) -> tuple[str, ...]:
    declared = target.get("required_api_families")
    if declared is not None:
        return tuple(sorted({str(item).split(".", 1)[0].casefold() for item in declared}))
    statement = str(target.get("task_statement", ""))
    return tuple(
        sorted(
            {
                match.group(1).split(".", 1)[0].casefold()
                for match in _EXPLICIT_DOTTED_API.finditer(statement)
            }
        )
    )


def _source_api_families(entry: Mapping[str, Any]) -> set[str]:
    values = {
        str(item).split(".", 1)[0].casefold()
        for item in entry.get("source_visible_libraries", ())
    }
    values.update(
        str(item).split(".", 1)[0].casefold() for item in entry.get("API_sequence", ())
    )
    repository = str(entry.get("repository_url", "")).removesuffix(".git").rsplit("/", 1)[-1]
    if repository:
        values.update({repository.casefold(), repository.casefold().replace("-", "_")})
    return values


def _target_leakage_terms(target: Mapping[str, Any]) -> tuple[str, ...]:
    terms = set(_required_api_families(target))
    for value in target.get("visible_target_symbols", ()):
        folded = str(value).casefold()
        if len(folded) >= 4 and folded not in _GENERIC_TARGET_SYMBOLS:
            terms.add(folded)
    for value in target.get("repository_visible_api_calls", ()):
        rendered = str(value).casefold()
        if "." in rendered:
            terms.add(rendered)
    return tuple(sorted(terms))


def _api_symbol_leakage(
    target: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[str, ...]:
    source_text = "\n".join(
        (
            str(entry.get("source_task_description", "")),
            str(entry.get("source_implementation_or_patch", "")),
        )
    ).casefold()
    tokens = {match.group(0).casefold() for match in _IDENTIFIER.finditer(source_text)}
    source_families = _source_api_families(entry)
    required = set(_required_api_families(target))
    leaks = []
    for term in _target_leakage_terms(target):
        leaked = term in source_text if "." in term else term in (
            source_families if term in required else tokens
        )
        if leaked:
            leaks.append(term)
    return tuple(leaks)


def _validation_evidence_bytes(entry: Mapping[str, Any]) -> int:
    evidence = entry.get("source_task_test", {})
    return len(
        json.dumps(
            {
                "command": evidence.get("command"),
                "stdout_utf8": evidence.get("stdout_utf8"),
                "stderr_utf8": evidence.get("stderr_utf8"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _metrics(entry: Mapping[str, Any], *, target_id: str) -> dict[str, int]:
    return {
        **memory_metrics(entry, target_id=target_id),
        "validation_evidence_bytes": _validation_evidence_bytes(entry),
    }


def _token_bin(value: int) -> int:
    for index, bound in enumerate(_TOKEN_BINS):
        if value <= bound:
            return index
    return len(_TOKEN_BINS)


def rank_irrelevant_memories_v3(
    target: Mapping[str, Any],
    relevant_entry: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
    scope: TargetIdentityScope,
    pair_safety_decision: Mapping[str, Any],
) -> dict[str, Any]:
    validate_b_only_mapping(target, target_identity_validator=scope.validate)
    target_id = str(target["benchmark_instance_id"])
    validate_source_correct_entry(relevant_entry, target_id=target_id)
    if (
        pair_safety_decision.get("status") != "PASS"
        or pair_safety_decision.get("top_source_id") != relevant_entry.get("source_id")
    ):
        raise SourcePairingV3Error("irrelevant selection requires passed locked-pair safety")
    target_date = _iso_date(target_b_date_utc)
    relevant_metrics = _metrics(relevant_entry, target_id=target_id)
    target_operations = set(_operations(target.get("operation_categories", ())))
    relevant_impl_hash = hashlib.sha256(
        str(relevant_entry["source_implementation_or_patch"]).encode("utf-8")
    ).hexdigest()
    relevant_task_hash = hashlib.sha256(
        str(relevant_entry["source_task_description"]).encode("utf-8")
    ).hexdigest()
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("source_id") == relevant_entry.get("source_id"):
            continue
        reasons: list[str] = []
        source_correct = True
        try:
            validate_source_correct_entry(entry, target_id=target_id)
        except SourcePairingError as error:
            source_correct = False
            reasons.append(f"SOURCE_CORRECT:{type(error).__name__}")
        historical_safety = entry.get("focal_source_safety", {})
        source_side_ab = bool(
            historical_safety.get("level") in {"A", "B"}
            and historical_safety.get("classification") == "PASS"
        )
        if not source_side_ab:
            reasons.append("SOURCE_SIDE_A_OR_B_SAFETY_EVIDENCE_ABSENT")
        metrics = _metrics(entry, target_id=target_id) if source_correct else None
        operations = set(_operations(entry.get("operation_class", ())))
        leaks = _api_symbol_leakage(target, entry)
        exact_duplicate = bool(
            hashlib.sha256(
                str(entry.get("source_implementation_or_patch", "")).encode("utf-8")
            ).hexdigest()
            == relevant_impl_hash
            or hashlib.sha256(
                str(entry.get("source_task_description", "")).encode("utf-8")
            ).hexdigest()
            == relevant_task_hash
        )
        if entry.get("language") != relevant_entry.get("language") or entry.get("language") != "python":
            reasons.append("LANGUAGE_INCOMPATIBLE")
        try:
            if _source_date(entry) > target_date:
                reasons.append("COARSE_TIMESTAMP_INELIGIBLE")
        except SourcePairingV3Error:
            reasons.append("COARSE_TIMESTAMP_INVALID")
        if target_operations & operations:
            reasons.append("TARGET_OPERATION_CLASS_OVERLAP")
        if leaks:
            reasons.append("TARGET_API_OR_SYMBOL_LEAKAGE")
        if exact_duplicate:
            reasons.append("RELEVANT_EPISODE_DUPLICATE")
        deltas = None
        if metrics is not None:
            deltas = {
                "packet_token_absolute_difference": abs(
                    metrics["packet_tokens"] - relevant_metrics["packet_tokens"]
                ),
                "implementation_byte_absolute_difference": abs(
                    metrics["implementation_bytes"] - relevant_metrics["implementation_bytes"]
                ),
                "validation_evidence_byte_absolute_difference": abs(
                    metrics["validation_evidence_bytes"]
                    - relevant_metrics["validation_evidence_bytes"]
                ),
                "token_bin_distance": abs(
                    _token_bin(metrics["packet_tokens"])
                    - _token_bin(relevant_metrics["packet_tokens"])
                ),
            }
        candidates.append(
            {
                "source_id": entry.get("source_id"),
                "source_entry_sha256": stable_record_hash(entry),
                "source_identity_sha256": _identity_hash(entry),
                "source_tier": _tier(entry, target_id),
                "hard_gate_pass": not reasons,
                "hard_gate_reasons": reasons,
                "source_correct": source_correct,
                "source_side_a_or_b_safety": source_side_ab,
                "operation_class_disjoint": not bool(target_operations & operations),
                "target_api_or_symbol_leakage": list(leaks),
                "same_packet_template": source_correct,
                "metrics": metrics,
                "deltas": deltas,
            }
        )
    candidates.sort(
        key=lambda row: (
            not row["hard_gate_pass"],
            float("inf")
            if row["deltas"] is None
            else row["deltas"]["packet_token_absolute_difference"],
            float("inf")
            if row["deltas"] is None
            else row["deltas"]["implementation_byte_absolute_difference"],
            float("inf")
            if row["deltas"] is None
            else row["deltas"]["validation_evidence_byte_absolute_difference"],
            _tier_number(str(row["source_tier"])),
            str(row["source_identity_sha256"]),
        )
    )
    for index, row in enumerate(candidates, 1):
        row["rank"] = index
    eligible = [row for row in candidates if row["hard_gate_pass"]]
    return {
        "schema": IRRELEVANT_SCHEMA_V3,
        "target_id": target_id,
        "target_b_date_utc": target_b_date_utc,
        "relevant_source_id": relevant_entry["source_id"],
        "status": "PASS" if eligible else "NOT_AVAILABLE",
        "selected_source_id": eligible[0]["source_id"] if eligible else None,
        "hard_gates": list(IRRELEVANT_HARD_GATES_V3),
        "selection": list(IRRELEVANT_SELECTION_V3),
        "fixed_length_tolerance": None,
        "same_template": True,
        "padding_or_truncation": False,
        "relevant_metrics": relevant_metrics,
        "candidate_rankings": candidates,
        "selection_uses_target_oracle": False,
        "selection_uses_model_outcome": False,
    }


def select_irrelevant_memory_v3(
    target: Mapping[str, Any],
    relevant_entry: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
    scope: TargetIdentityScope,
    pair_safety_decision: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Any], dict[str, Any]]:
    record = rank_irrelevant_memories_v3(
        target,
        relevant_entry,
        entries,
        target_b_date_utc=target_b_date_utc,
        scope=scope,
        pair_safety_decision=pair_safety_decision,
    )
    source_id = record["selected_source_id"]
    if record["status"] != "PASS" or not source_id:
        raise SourcePairingV3Error("NO_ELIGIBLE_IRRELEVANT_MEMORY")
    matches = [entry for entry in entries if entry.get("source_id") == source_id]
    if len(matches) != 1:
        raise SourcePairingV3Error("selected irrelevant source is not unique")
    selected = matches[0]
    render_memory_packet(selected, target_id=str(target["benchmark_instance_id"]))
    lock_body = {
        "schema": IRRELEVANT_LOCK_SCHEMA_V3,
        "target_id": target["benchmark_instance_id"],
        "target_scope_purpose": scope.purpose,
        "target_identity_list_sha256": scope.identity_list_sha256,
        "relevant_source_id": relevant_entry["source_id"],
        "selected_source_id": source_id,
        "selected_source_entry_sha256": stable_record_hash(selected),
        "prepared_source_corpus_sha256": corpus_manifest_hash(entries),
        "selection_design_sha256": stable_record_hash(
            {
                "hard_gates": IRRELEVANT_HARD_GATES_V3,
                "selection": IRRELEVANT_SELECTION_V3,
                "fixed_length_tolerance": None,
            }
        ),
        "candidate_rankings_sha256": stable_record_hash(record["candidate_rankings"]),
        "target_b_date_utc": target_b_date_utc,
        "top_one": True,
        "rank_2_fallback": False,
    }
    return selected, record, {**lock_body, "lock_hash": stable_record_hash(lock_body)}


def enforce_irrelevant_lock_v3(
    lock: Mapping[str, Any], requested_source_id: str
) -> None:
    if lock.get("schema") != IRRELEVANT_LOCK_SCHEMA_V3:
        raise SourcePairingV3Error("V3 irrelevant lock schema mismatch")
    if requested_source_id != lock.get("selected_source_id"):
        raise PermissionError("irrelevant rank-2/manual fallback is forbidden")
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise SourcePairingV3Error("irrelevant top-one policy changed")
    body = {key: value for key, value in lock.items() if key != "lock_hash"}
    if stable_record_hash(body) != lock.get("lock_hash"):
        raise SourcePairingV3Error("V3 irrelevant lock hash mismatch")


def validate_locked_irrelevant_timestamp_v3(
    lock: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_timestamp_epoch: int,
) -> dict[str, Any]:
    source_id = str(lock.get("selected_source_id", ""))
    enforce_irrelevant_lock_v3(lock, source_id)
    matches = [entry for entry in entries if entry.get("source_id") == source_id]
    if len(matches) != 1:
        raise SourcePairingV3Error("locked irrelevant source does not resolve uniquely")
    status = "PASS"
    try:
        validate_timestamp(matches[0].get("commit_timestamp_epoch"), target_b_timestamp_epoch)
    except SourcePairingError:
        status = "REJECT_POSTDATED_NO_FALLBACK"
    return {
        "schema": "cmpilot-sealed-exact-timestamp-validation-v3",
        "lock_kind": "IRRELEVANT_MATCH_V3",
        "lock_sha256": stable_record_hash(lock),
        "source_id": source_id,
        "source_timestamp_epoch": matches[0].get("commit_timestamp_epoch"),
        "target_b_timestamp_epoch": target_b_timestamp_epoch,
        "status": status,
        "fallback_attempted": False,
    }
