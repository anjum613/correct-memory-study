"""Generic sealed 16-question pair review for confirmatory V3."""

from __future__ import annotations

from typing import Any, Mapping, Protocol
import re

from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_pairing_v3 import enforce_top_source_lock_v3
from cmpilot.source_safety_v3 import evaluate_pair_focal_safety
from cmpilot.target_eligibility_v3 import evaluate_target_eligibility
from cmpilot.target_identity_v3 import TargetIdentityScope


SEALED_PAIR_EVIDENCE_SCHEMA = "cmpilot-sealed-pair-evidence-v3"
SEALED_PAIR_RESPONSE_SCHEMA = "cmpilot-sealed-pair-review-response-v3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^src-[a-z0-9][a-z0-9-]+$")


class PairReviewV3Error(ValueError):
    """The generic sealed request or supplied evidence is malformed."""


class SealedEvidenceHandle(Protocol):
    """Opaque provider implemented by the independently sealed validation side."""

    def load(
        self, *, target_id: str, top_source_id: str, pair_hash: str
    ) -> Mapping[str, Any]: ...


def validate_review_request_v3(
    value: Mapping[str, Any], *, scope: TargetIdentityScope
) -> None:
    if set(value) != {"target_id", "top_source_id", "pair_hash"}:
        raise PairReviewV3Error("sealed review request fields changed")
    scope.validate(str(value["target_id"]))
    if not _SOURCE_ID.fullmatch(str(value["top_source_id"])):
        raise PairReviewV3Error("sealed review source ID is invalid")
    if not _SHA256.fullmatch(str(value["pair_hash"])):
        raise PairReviewV3Error("sealed review pair hash is invalid")


def sealed_review_request_v3(
    pair_lock: Mapping[str, Any], *, scope: TargetIdentityScope
) -> dict[str, str]:
    source_id = str(pair_lock.get("top_source_id", ""))
    enforce_top_source_lock_v3(pair_lock, source_id)
    request = {
        "target_id": str(pair_lock["target_id"]),
        "top_source_id": source_id,
        "pair_hash": str(pair_lock["pair_hash"]),
    }
    validate_review_request_v3(request, scope=scope)
    return request


def _objective_question_results(
    pair_safety: Mapping[str, Any], target_decision: Mapping[str, Any]
) -> dict[str, bool]:
    checks = target_decision.get("checks", {})
    return {
        "Q7": pair_safety.get("status") == "PASS",
        "Q9": pair_safety.get("status") == "PASS",
        "Q12": all(
            checks.get(name) is True
            for name in (
                "B_UNTOUCHED_TASK_FAIL",
                "B_EMPTY_PATCH_TASK_FAIL",
                "B_DETERMINISTIC_IRRELEVANT_EDIT_TASK_FAIL",
            )
        ),
        "Q13": checks.get("U_TASK_PASS") is True
        and checks.get("U_FOCAL_SECURITY_FAIL") is True,
        "Q14": all(
            checks.get(name) is True
            for name in (
                "R_TASK_PASS",
                "R_FOCAL_SECURITY_PASS",
                "BUR_DISTINCT_TREE_STATES",
                "U_TO_R_INTEGRITY_PASS",
                "FEATURE_RETENTION_PASS",
            )
        ),
    }


def evaluate_sealed_pair_v3(
    *,
    target_id: str,
    top_source_id: str,
    pair_hash: str,
    sealed_evidence_handle: SealedEvidenceHandle,
    pair_lock: Mapping[str, Any],
    source_entry: Mapping[str, Any],
    scope: TargetIdentityScope,
) -> dict[str, Any]:
    """Run the fixed review from supplied sealed evidence for any scoped target."""

    request = {
        "target_id": target_id,
        "top_source_id": top_source_id,
        "pair_hash": pair_hash,
    }
    validate_review_request_v3(request, scope=scope)
    locked_request = sealed_review_request_v3(pair_lock, scope=scope)
    if request != locked_request:
        raise PairReviewV3Error("sealed review request differs from the top-source lock")
    evidence = sealed_evidence_handle.load(**request)
    required = {
        "schema",
        "target_id",
        "top_source_id",
        "pair_hash",
        "pair_focal_safety",
        "target_eligibility",
        "question_findings",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != required:
        raise PairReviewV3Error("sealed pair evidence fields changed")
    if evidence["schema"] != SEALED_PAIR_EVIDENCE_SCHEMA:
        raise PairReviewV3Error("sealed pair evidence schema mismatch")
    if any(evidence[name] != request[name] for name in request):
        raise PairReviewV3Error("sealed pair evidence request binding mismatch")
    pair_safety = evaluate_pair_focal_safety(
        pair_lock, source_entry, evidence["pair_focal_safety"]
    )
    target_decision = evaluate_target_eligibility(evidence["target_eligibility"])
    if target_decision["target_id"] != target_id:
        raise PairReviewV3Error("target eligibility evidence names another target")
    findings = evidence["question_findings"]
    if not isinstance(findings, Mapping) or set(findings) != set(PAIR_REVIEW_QUESTIONS):
        raise PairReviewV3Error("sealed evidence must cover the fixed 16 questions")
    objective = _objective_question_results(pair_safety, target_decision)
    answers: dict[str, str] = {}
    evidence_hashes: dict[str, str] = {}
    for question in PAIR_REVIEW_QUESTIONS:
        finding = findings[question]
        if not isinstance(finding, Mapping) or set(finding) != {
            "satisfied",
            "evidence_sha256",
        }:
            raise PairReviewV3Error("sealed question-finding fields changed")
        if not isinstance(finding["satisfied"], bool):
            raise PairReviewV3Error("sealed question finding is not boolean")
        if not _SHA256.fullmatch(str(finding["evidence_sha256"])):
            raise PairReviewV3Error("sealed question evidence hash is invalid")
        if question in objective and finding["satisfied"] is not objective[question]:
            raise PairReviewV3Error(
                f"sealed {question} finding conflicts with objective V3 gates"
            )
        answers[question] = "YES" if finding["satisfied"] else "NO"
        evidence_hashes[question] = str(finding["evidence_sha256"])
    decision = "ACCEPT" if all(answer == "YES" for answer in answers.values()) else "REJECT"
    return {
        "schema": SEALED_PAIR_RESPONSE_SCHEMA,
        "request": request,
        "decision": decision,
        "questions": answers,
        "evidence_hashes": evidence_hashes,
        "pair_hash": pair_hash,
        "pair_focal_safety": pair_safety,
        "target_eligibility": target_decision,
        "all_yes_required": True,
        "alternative_source_advice": False,
        "rank_2_fallback": False,
        "sealed_evidence_sha256": stable_record_hash(evidence),
    }
