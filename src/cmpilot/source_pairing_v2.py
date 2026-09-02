"""Threshold-free B-only matching and irrelevant controls for development V2.

The module accepts public B-only representations and validated frozen source
entries.  It deliberately has no oracle reader, model client, network client,
rank-2 API, or weighted/global similarity score.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from cmpilot.memory_lifecycle import memory_metrics, render_memory_packet
from cmpilot.source_corpus_v2 import PROTOCOL_ID, SUCCESSOR_PROTOCOL_COMMIT
from cmpilot.source_pairing import (
    SourcePairingError,
    cosine_similarity,
    jaccard_similarity,
    multiset_jaccard,
    ordered_lcs_similarity,
    stable_record_hash,
    token_shingles,
    validate_b_only_mapping,
)
from cmpilot.source_validation import (
    corpus_manifest_hash,
    validate_source_entry,
    validate_timestamp,
)


MATCHER_SCHEMA = "cmpilot-b-only-lexicographic-matcher-v2"
PAIR_LOCK_SCHEMA = "cmpilot-source-pair-lock-v2"
IRRELEVANT_SCHEMA = "cmpilot-irrelevant-memory-selection-v2"
IRRELEVANT_LOCK_SCHEMA = "cmpilot-irrelevant-memory-lock-v2"
GLOBAL_SIMILARITY_THRESHOLD_REQUIRED = False

MEANINGFUL_RANKING_DIMENSIONS = (
    "primary_operation_class_exact",
    "operation_class_intersection_count",
    "same_required_or_public_library_api",
    "api_sequence_similarity",
    "type_data_role_similarity",
    "ast_similarity",
    "token_similarity",
    "semantic_similarity",
)

LEXICOGRAPHIC_RANKING = (
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

HARD_GATES = (
    "FROZEN_CORPUS_MEMBERSHIP_AND_HASH",
    "LANGUAGE_EXACT_PYTHON",
    "COARSE_TIMESTAMP_DATE",
    "REAL_RECONSTRUCTIBLE_SOURCE_BUILD_PASS",
    "SOURCE_TASK_TEST_PASS_AND_FOCAL_SAFETY_A_TO_C_PASS",
    "NONEMPTY_CONTROLLED_OPERATION_CLASS_INTERSECTION",
    "REQUIRED_LIBRARY_API_MATCH_WHEN_MARKED_REQUIRED",
)

IRRELEVANT_HARD_GATES = (
    "REAL_SOURCE",
    "EXECUTABLE_AND_VALIDATED",
    "SAME_LANGUAGE",
    "SAME_PACKET_TEMPLATE",
    "COARSE_TIMESTAMP_DATE",
    "NO_OPERATION_CLASS_INTERSECTION",
    "NO_TARGET_API_OR_SYMBOL_LEAKAGE",
    "NOT_RELEVANT_SOURCE_OR_EXACT_DUPLICATE",
)

IRRELEVANT_SELECTION = (
    "ABS_PACKET_LEXICAL_TOKEN_DIFFERENCE_ASC",
    "ABS_IMPLEMENTATION_BYTE_DIFFERENCE_ASC",
    "ABS_VALIDATION_EVIDENCE_BYTE_DIFFERENCE_ASC",
    "SOURCE_TIER_ASC",
    "CANONICAL_SOURCE_IDENTITY_SHA256_ASC",
)

_OPERATION_ALIASES = {
    "MARKUP_SERIALIZATION": "MARKUP_LINK_SERIALIZATION",
    "AUTHENTICATION_AUTHORIZATION": "AUTHENTICATION_FLOW",
}
_EXPLICIT_DOTTED_API = re.compile(
    r"`((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)`"
)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
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
_TOKEN_BINS = (0, 256, 512, 1024, 2048, 4096, 8192, 16384)


class SourcePairingV2Error(SourcePairingError):
    """A frozen V2 matching or control invariant failed."""


def _canonical_operation(value: str) -> str:
    return _OPERATION_ALIASES.get(value, value)


def _operation_tuple(value: Iterable[Any]) -> tuple[str, ...]:
    return tuple(_canonical_operation(str(item)) for item in value)


def _iso_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SourcePairingV2Error("target B date must be YYYY-MM-DD UTC metadata")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SourcePairingV2Error("target B date is invalid") from error


def _source_utc_date(entry: Mapping[str, Any]) -> date:
    try:
        parsed = datetime.fromisoformat(str(entry["commit_timestamp"]))
    except (KeyError, ValueError) as error:
        raise SourcePairingV2Error("source timestamp is absent or invalid") from error
    if parsed.tzinfo is None:
        raise SourcePairingV2Error("source timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).date()


def _tier(entry: Mapping[str, Any], target_id: str) -> str:
    tiers = entry.get("source_tier_by_target")
    if not isinstance(tiers, Mapping) or target_id not in tiers:
        raise SourcePairingV2Error("source tier is absent for target")
    value = str(tiers[target_id])
    if value not in {"S1", "S2", "S3"}:
        raise SourcePairingV2Error("source tier is invalid")
    return value


def _tier_number(value: str) -> int:
    if value not in {"S1", "S2", "S3"}:
        raise SourcePairingV2Error("source tier is invalid")
    return int(value[1])


def required_api_families(target: Mapping[str, Any]) -> tuple[str, ...]:
    """Derive only explicit public-task requirements, never visible coincidence."""

    declared = target.get("required_api_families")
    if declared is not None:
        if not isinstance(declared, list) or not all(
            isinstance(item, str) and item for item in declared
        ):
            raise SourcePairingV2Error("required API families must be a string list")
        return tuple(sorted({item.split(".", 1)[0].casefold() for item in declared}))
    statement = str(target.get("task_statement", ""))
    return tuple(
        sorted(
            {
                match.group(1).split(".", 1)[0].casefold()
                for match in _EXPLICIT_DOTTED_API.finditer(statement)
            }
        )
    )


def _source_api_families(entry: Mapping[str, Any]) -> tuple[str, ...]:
    values = {str(item).split(".", 1)[0].casefold() for item in entry.get("source_visible_libraries", ())}
    values.update(
        str(item).split(".", 1)[0].casefold() for item in entry.get("API_sequence", ())
    )
    repository = str(entry.get("repository_url", "")).removesuffix(".git").rsplit("/", 1)[-1]
    if repository:
        values.add(repository.casefold().replace("-", "_"))
        values.add(repository.casefold())
    return tuple(sorted(values))


def _target_public_families(target: Mapping[str, Any]) -> tuple[str, ...]:
    values = {
        str(item).split(".", 1)[0].casefold()
        for item in target.get("repository_visible_libraries", ())
    }
    values.update(required_api_families(target))
    return tuple(sorted(values))


def score_candidate_v2(
    target: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, float | int | bool]:
    target_operations = _operation_tuple(target.get("operation_categories", ()))
    source_operations = _operation_tuple(entry.get("operation_class", ()))
    target_primary = _canonical_operation(str(target.get("task_described_operation", "")))
    source_primary = source_operations[0] if source_operations else ""
    target_apis = tuple(str(item) for item in target.get("repository_visible_api_calls", ()))
    source_apis = tuple(str(item) for item in entry.get("API_sequence", ()))
    target_roles = tuple(str(item) for item in target.get("types_and_data_roles", ()))
    source_roles = tuple(str(item) for item in entry.get("type_or_data_role_signature", ()))
    target_ast = tuple(str(item) for item in target.get("ast_structure", ()))
    source_ast = tuple(str(item) for item in entry.get("AST_signature", ()))
    target_vector = target.get("task_semantic_embedding", {}).get("vector", ())
    source_vector = entry.get("source_semantic_vector", ())
    target_text = "\n".join(
        (
            str(target.get("task_statement", "")),
            " ".join(str(item) for item in target.get("visible_target_symbols", ())),
            " ".join(target_apis),
        )
    )
    required = set(required_api_families(target))
    source_families = set(_source_api_families(entry))
    public_families = set(_target_public_families(target))
    return {
        "language_exact": target.get("language") == entry.get("language") == "python",
        "primary_operation_class_exact": bool(source_primary and source_primary == target_primary),
        "operation_class_intersection_count": len(set(target_operations) & set(source_operations)),
        "required_api_present": bool(required),
        "required_api_match": not required or bool(required & source_families),
        "same_required_or_public_library_api": bool(public_families & source_families),
        "api_sequence_similarity": round(ordered_lcs_similarity(target_apis, source_apis), 12),
        "type_data_role_similarity": round(multiset_jaccard(target_roles, source_roles), 12),
        "ast_similarity": round(multiset_jaccard(target_ast, source_ast), 12),
        "token_similarity": round(
            jaccard_similarity(token_shingles(target_text), entry.get("normalized_token_signature", ())),
            12,
        ),
        "semantic_similarity": round(cosine_similarity(target_vector, source_vector), 12),
    }


def _source_validation_gate(entry: Mapping[str, Any]) -> tuple[bool, str | None]:
    try:
        validate_source_entry(entry, confirmatory=True)
    except SourcePairingError as error:
        return False, f"SOURCE_VALIDATION:{type(error).__name__}"
    return True, None


def _hard_gate_reasons(
    target: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    target_b_date_utc: str,
    scores: Mapping[str, Any],
) -> tuple[str, ...]:
    reasons: list[str] = []
    valid, validation_reason = _source_validation_gate(entry)
    if not valid:
        reasons.append(str(validation_reason))
    if not scores["language_exact"]:
        reasons.append("LANGUAGE_INCOMPATIBLE")
    try:
        if _source_utc_date(entry) > _iso_date(target_b_date_utc):
            reasons.append("COARSE_TIMESTAMP_INELIGIBLE")
    except SourcePairingV2Error:
        reasons.append("COARSE_TIMESTAMP_INVALID")
    if int(scores["operation_class_intersection_count"]) < 1:
        reasons.append("OPERATION_CLASS_INCOMPATIBLE")
    if not scores["required_api_match"]:
        reasons.append("REQUIRED_API_INCOMPATIBLE")
    return tuple(reasons)


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


def _meaningful_vector(scores: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(scores[name] for name in MEANINGFUL_RANKING_DIMENSIONS)


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


def scientific_equivalence_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    pstar = entry.get("focal_source_safety", {}).get("pstar", {})
    return (
        _operation_tuple(entry.get("operation_class", ())),
        tuple(str(item) for item in entry.get("API_sequence", ())),
        tuple(str(item) for item in entry.get("type_or_data_role_signature", ())),
        pstar.get("ontology_class"),
        hashlib.sha256(
            str(entry.get("source_implementation_or_patch", "")).encode("utf-8")
        ).hexdigest(),
        hashlib.sha256(
            str(entry.get("source_task_description", "")).encode("utf-8")
        ).hexdigest(),
    )


def resolve_top_ambiguity(
    top: Mapping[str, Any],
    runner_up: Mapping[str, Any],
    entries_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Interpret an exact scientific-rank tie without numerical margins."""

    if _meaningful_vector(top["scores"]) != _meaningful_vector(runner_up["scores"]):
        return {"status": "UNAMBIGUOUS_FIRST_MEANINGFUL_DIFFERENCE", "hash_tiebreak_used": False}
    top_entry = entries_by_id[str(top["source_id"])]
    runner_entry = entries_by_id[str(runner_up["source_id"])]
    equivalent = scientific_equivalence_key(top_entry) == scientific_equivalence_key(runner_entry)
    if not equivalent:
        raise SourcePairingV2Error("MATCH_AMBIGUOUS_SUBSTANTIVE_TIE")
    return {"status": "EQUIVALENT_EPISODE_HASH_TIEBREAK", "hash_tiebreak_used": True}


def matcher_design_record() -> dict[str, Any]:
    return {
        "schema": MATCHER_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "b_only": True,
        "hard_gates": list(HARD_GATES),
        "ranking": list(LEXICOGRAPHIC_RANKING),
        "meaningful_dimensions": list(MEANINGFUL_RANKING_DIMENSIONS),
        "global_similarity_threshold_required": False,
        "combined_or_weighted_score": None,
        "numerical_ambiguity_margin": None,
        "ambiguity_rule": (
            "REJECT_EXACT_MEANINGFUL_TIE_UNLESS_SCIENTIFIC_EQUIVALENCE_KEY_IDENTICAL"
        ),
        "top_one": True,
        "rank_2_fallback": False,
        "manual_fallback": False,
        "oracle_features": [],
    }


def rank_sources_v2(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
) -> list[dict[str, Any]]:
    validate_b_only_mapping(target)
    _iso_date(target_b_date_utc)
    expected_corpus_hash = corpus_manifest_hash(entries)
    if not entries:
        raise SourcePairingV2Error("source corpus cannot be empty")
    target_id = str(target["benchmark_instance_id"])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        source_id = str(entry.get("source_id", ""))
        if not source_id or source_id in seen:
            raise SourcePairingV2Error("source IDs must be nonempty and unique")
        seen.add(source_id)
        scores = score_candidate_v2(target, entry)
        reasons = _hard_gate_reasons(
            target,
            entry,
            target_b_date_utc=target_b_date_utc,
            scores=scores,
        )
        rows.append(
            {
                "source_id": source_id,
                "source_entry_sha256": stable_record_hash(entry),
                "source_identity_sha256": _identity_hash(entry),
                "source_tier": _tier(entry, target_id),
                "hard_gate_pass": not reasons,
                "hard_gate_reasons": list(reasons),
                "scores": scores,
                "global_or_weighted_score": None,
            }
        )
    rows.sort(key=lambda row: (not row["hard_gate_pass"], _rank_key(row)))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
        row["corpus_sha256"] = expected_corpus_hash
    return rows


def select_top_source_v2(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rankings = rank_sources_v2(target, entries, target_b_date_utc=target_b_date_utc)
    eligible = [row for row in rankings if row["hard_gate_pass"]]
    if not eligible:
        raise SourcePairingV2Error("NO_SOURCE_PASSES_HARD_GATES")
    entries_by_id = {str(entry["source_id"]): entry for entry in entries}
    ambiguity = (
        {"status": "SINGLE_ELIGIBLE_SOURCE", "hash_tiebreak_used": False}
        if len(eligible) == 1
        else resolve_top_ambiguity(eligible[0], eligible[1], entries_by_id)
    )
    top = eligible[0]
    design = matcher_design_record()
    corpus_hash = corpus_manifest_hash(entries)
    target_date_record = {
        "field": "target_b_date_utc",
        "value": target_b_date_utc,
        "target_commit_hash_exposed": False,
    }
    lock_body = {
        "schema": PAIR_LOCK_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "target_id": target["benchmark_instance_id"],
        "top_source_id": top["source_id"],
        "top_source_entry_sha256": top["source_entry_sha256"],
        "target_representation_sha256": stable_record_hash(target),
        "target_date_metadata_sha256": stable_record_hash(target_date_record),
        "source_corpus_sha256": corpus_hash,
        "matcher_design_sha256": stable_record_hash(design),
        "full_rankings_sha256": stable_record_hash(rankings),
        "ambiguity": ambiguity,
        "global_similarity_threshold": None,
        "top_one": True,
        "rank_2_fallback": False,
    }
    return rankings, {**lock_body, "pair_hash": stable_record_hash(lock_body)}


def enforce_top_source_lock_v2(
    lock: Mapping[str, Any], requested_source_id: str
) -> None:
    if lock.get("schema") != PAIR_LOCK_SCHEMA:
        raise SourcePairingV2Error("V2 pair lock schema mismatch")
    if requested_source_id != lock.get("top_source_id"):
        raise PermissionError("rank-2/manual source fallback is forbidden")
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise SourcePairingV2Error("top-one lock policy changed")
    body = {key: value for key, value in lock.items() if key != "pair_hash"}
    if stable_record_hash(body) != lock.get("pair_hash"):
        raise SourcePairingV2Error("V2 pair lock hash mismatch")


def _exact_timestamp_record(
    *,
    lock: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    target_b_timestamp_epoch: int,
    lock_kind: str,
) -> dict[str, Any]:
    if lock_kind == "PAIR_TOP_ONE_V2":
        source_id = str(lock.get("top_source_id", ""))
        enforce_top_source_lock_v2(lock, source_id)
    elif lock_kind == "IRRELEVANT_MATCH_V2":
        source_id = str(lock.get("selected_source_id", ""))
        enforce_irrelevant_lock_v2(lock, source_id)
    else:
        raise SourcePairingV2Error("unknown V2 lock kind")
    matches = [entry for entry in entries if entry.get("source_id") == source_id]
    if len(matches) != 1:
        raise SourcePairingV2Error("locked source does not resolve uniquely")
    source_epoch = matches[0].get("commit_timestamp_epoch")
    status = "PASS"
    try:
        validate_timestamp(source_epoch, target_b_timestamp_epoch)
    except SourcePairingError:
        status = "REJECT_POSTDATED_NO_FALLBACK"
    return {
        "schema": "cmpilot-sealed-exact-timestamp-validation-v2",
        "lock_kind": lock_kind,
        "lock_sha256": stable_record_hash(lock),
        "source_id": source_id,
        "source_timestamp_epoch": source_epoch,
        "target_b_timestamp_epoch": target_b_timestamp_epoch,
        "status": status,
        "fallback_attempted": False,
    }


def validate_locked_source_timestamp(
    lock: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_timestamp_epoch: int,
) -> dict[str, Any]:
    return _exact_timestamp_record(
        lock=lock,
        entries=entries,
        target_b_timestamp_epoch=target_b_timestamp_epoch,
        lock_kind="PAIR_TOP_ONE_V2",
    )


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


def _target_leakage_terms(target: Mapping[str, Any]) -> tuple[str, ...]:
    terms: set[str] = set(required_api_families(target))
    for value in target.get("visible_target_symbols", ()):
        folded = str(value).casefold()
        if len(folded) >= 4 and folded not in _GENERIC_TARGET_SYMBOLS:
            terms.add(folded)
    for value in target.get("repository_visible_api_calls", ()):
        string = str(value).casefold()
        if "." in string:
            terms.add(string)
    return tuple(sorted(terms))


def _entry_identifier_tokens(entry: Mapping[str, Any]) -> set[str]:
    text = "\n".join(
        (
            str(entry.get("source_task_description", "")),
            str(entry.get("source_implementation_or_patch", "")),
        )
    )
    return {match.group(0).casefold() for match in _IDENTIFIER.finditer(text)}


def _api_symbol_leakage(
    target: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[str, ...]:
    tokens = _entry_identifier_tokens(entry)
    source_text = "\n".join(
        (
            str(entry.get("source_task_description", "")),
            str(entry.get("source_implementation_or_patch", "")),
        )
    ).casefold()
    source_families = set(_source_api_families(entry))
    leaks = []
    for term in _target_leakage_terms(target):
        if "." in term:
            leaked = term in source_text
        elif term in required_api_families(target):
            leaked = term in source_families
        else:
            leaked = term in tokens
        if leaked:
            leaks.append(term)
    return tuple(leaks)


def _irrelevant_metrics(entry: Mapping[str, Any]) -> dict[str, int]:
    values = memory_metrics(entry)
    return {**values, "validation_evidence_bytes": _validation_evidence_bytes(entry)}


def _token_bin(value: int) -> int:
    for index, bound in enumerate(_TOKEN_BINS):
        if value <= bound:
            return index
    return len(_TOKEN_BINS)


def rank_irrelevant_memories_v2(
    target: Mapping[str, Any],
    relevant_entry: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
) -> dict[str, Any]:
    validate_b_only_mapping(target)
    validate_source_entry(relevant_entry, confirmatory=True)
    _iso_date(target_b_date_utc)
    target_id = str(target["benchmark_instance_id"])
    relevant_metrics = _irrelevant_metrics(relevant_entry)
    relevant_operations = set(_operation_tuple(target.get("operation_categories", ())))
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
        validation_pass, validation_reason = _source_validation_gate(entry)
        metrics = _irrelevant_metrics(entry) if validation_pass else None
        operations = set(_operation_tuple(entry.get("operation_class", ())))
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
        reasons: list[str] = []
        if not validation_pass:
            reasons.append(str(validation_reason))
        if entry.get("language") != relevant_entry.get("language") or entry.get("language") != "python":
            reasons.append("LANGUAGE_INCOMPATIBLE")
        try:
            if _source_utc_date(entry) > _iso_date(target_b_date_utc):
                reasons.append("COARSE_TIMESTAMP_INELIGIBLE")
        except SourcePairingV2Error:
            reasons.append("COARSE_TIMESTAMP_INVALID")
        if relevant_operations & operations:
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
                    metrics["implementation_bytes"]
                    - relevant_metrics["implementation_bytes"]
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
                "operation_class_disjoint": not bool(relevant_operations & operations),
                "target_api_or_symbol_leakage": list(leaks),
                "same_packet_template": validation_pass,
                "metrics": metrics,
                "deltas": deltas,
            }
        )
    candidates.sort(
        key=lambda row: (
            not row["hard_gate_pass"],
            float("inf") if row["deltas"] is None else row["deltas"]["packet_token_absolute_difference"],
            float("inf") if row["deltas"] is None else row["deltas"]["implementation_byte_absolute_difference"],
            float("inf") if row["deltas"] is None else row["deltas"]["validation_evidence_byte_absolute_difference"],
            _tier_number(str(row["source_tier"])),
            str(row["source_identity_sha256"]),
        )
    )
    for index, row in enumerate(candidates, 1):
        row["rank"] = index
    eligible = [row for row in candidates if row["hard_gate_pass"]]

    implementation_first = sorted(
        eligible,
        key=lambda row: (
            row["deltas"]["implementation_byte_absolute_difference"],
            row["deltas"]["packet_token_absolute_difference"],
            row["source_identity_sha256"],
        ),
    )
    coarse_bins = sorted(
        eligible,
        key=lambda row: (
            row["deltas"]["token_bin_distance"],
            row["deltas"]["packet_token_absolute_difference"],
            row["source_identity_sha256"],
        ),
    )
    return {
        "schema": IRRELEVANT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "target_id": target_id,
        "target_b_date_utc": target_b_date_utc,
        "target_commit_hash_exposed": False,
        "relevant_source_id": relevant_entry["source_id"],
        "status": "PASS" if eligible else "NOT_AVAILABLE",
        "selected_source_id": eligible[0]["source_id"] if eligible else None,
        "hard_gates": list(IRRELEVANT_HARD_GATES),
        "selection": list(IRRELEVANT_SELECTION),
        "fixed_length_tolerance": None,
        "same_template": True,
        "padding_or_truncation": False,
        "relevant_metrics": relevant_metrics,
        "candidate_rankings": candidates,
        "sensitivity_only": {
            "implementation_size_then_token": (
                implementation_first[0]["source_id"] if implementation_first else None
            ),
            "coarse_token_bins": coarse_bins[0]["source_id"] if coarse_bins else None,
            "can_change_primary_selection": False,
        },
        "selection_uses_target_oracle": False,
        "selection_uses_model_outcome": False,
    }


def select_irrelevant_memory_v2(
    target: Mapping[str, Any],
    relevant_entry: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_date_utc: str,
) -> tuple[Mapping[str, Any], dict[str, Any], dict[str, Any]]:
    record = rank_irrelevant_memories_v2(
        target,
        relevant_entry,
        entries,
        target_b_date_utc=target_b_date_utc,
    )
    source_id = record["selected_source_id"]
    if record["status"] != "PASS" or not source_id:
        raise SourcePairingV2Error("NO_TIMESTAMP_ELIGIBLE_IRRELEVANT_MEMORY")
    matches = [entry for entry in entries if entry.get("source_id") == source_id]
    if len(matches) != 1:
        raise SourcePairingV2Error("selected irrelevant source is not unique")
    selected = matches[0]
    render_memory_packet(selected)
    lock_body = {
        "schema": IRRELEVANT_LOCK_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "target_id": target["benchmark_instance_id"],
        "relevant_source_id": relevant_entry["source_id"],
        "selected_source_id": source_id,
        "selected_source_entry_sha256": stable_record_hash(selected),
        "source_corpus_sha256": corpus_manifest_hash(entries),
        "selection_design_sha256": stable_record_hash(
            {
                "hard_gates": IRRELEVANT_HARD_GATES,
                "selection": IRRELEVANT_SELECTION,
                "fixed_length_tolerance": None,
            }
        ),
        "candidate_rankings_sha256": stable_record_hash(record["candidate_rankings"]),
        "target_date_metadata_sha256": stable_record_hash(
            {"target_b_date_utc": target_b_date_utc, "target_commit_hash_exposed": False}
        ),
        "top_one": True,
        "rank_2_fallback": False,
    }
    lock = {**lock_body, "lock_hash": stable_record_hash(lock_body)}
    return selected, record, lock


def enforce_irrelevant_lock_v2(
    lock: Mapping[str, Any], requested_source_id: str
) -> None:
    if lock.get("schema") != IRRELEVANT_LOCK_SCHEMA:
        raise SourcePairingV2Error("V2 irrelevant lock schema mismatch")
    if requested_source_id != lock.get("selected_source_id"):
        raise PermissionError("irrelevant rank-2/manual fallback is forbidden")
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise SourcePairingV2Error("irrelevant top-one policy changed")
    body = {key: value for key, value in lock.items() if key != "lock_hash"}
    if stable_record_hash(body) != lock.get("lock_hash"):
        raise SourcePairingV2Error("V2 irrelevant lock hash mismatch")


def validate_locked_irrelevant_timestamp(
    lock: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_b_timestamp_epoch: int,
) -> dict[str, Any]:
    return _exact_timestamp_record(
        lock=lock,
        entries=entries,
        target_b_timestamp_epoch=target_b_timestamp_epoch,
        lock_kind="IRRELEVANT_MATCH_V2",
    )
