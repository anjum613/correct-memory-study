#!/usr/bin/env python3
"""Fail closed when publication derivatives diverge from frozen evidence."""

from __future__ import annotations

import csv
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_ROOT = REPO_ROOT / "paper"
STARTING_COMMIT = "b10c7801b05939811e2584418806316fbff01fdc"
CLAIM_LEDGER_FREEZE_COMMIT = "0ad9819cef03bbfa4e66c480e3036601839ca158"
PAPER_IDS = (
    "BASM_WHEN_NOT_TO_IMITATE",
    "AGENT_SKILLS_CAN_BE_HARMFUL",
    "SLBENCH",
    "SWE_SKILLS_BENCH",
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY",
    "SECUREVIBEBENCH",
)
STATUS_VOCABULARY = {
    "ESTABLISHED",
    "NOT_ESTABLISHED",
    "UNDETERMINED",
    "NOT_APPLICABLE",
}
REQUIRED_CLAIM_FIELDS = {
    "CLAIM_ID",
    "CLAIM_TEXT",
    "INFERENTIAL_STATUS",
    "SUPPORTING_ARTIFACTS",
    "NUMERIC_EVIDENCE",
    "ALLOWED_SCOPE",
    "PROHIBITED_GENERALIZATION",
}


class EvidenceValidationError(AssertionError):
    """A paper claim or derivative is inconsistent with frozen evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceValidationError(message)


def _yaml(path: Path) -> Any:
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _flatten_scalars(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _flatten_scalars(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_scalars(item)
    elif value is not None:
        yield str(value)


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def validate_claim_ledger() -> None:
    path = PAPER_ROOT / "claim-ledger.yaml"
    frozen = _git("show", f"{CLAIM_LEDGER_FREEZE_COMMIT}:paper/claim-ledger.yaml")
    _require(path.read_text(encoding="utf-8") == frozen, "claim ledger changed after its freeze commit")
    ledger = _yaml(path)
    _require(ledger["BASE_COMMIT"] == STARTING_COMMIT, "claim ledger base commit changed")
    claims = ledger["CLAIMS"]
    _require(len(claims) >= 14, "fewer than fourteen required claims")
    _require(
        all(REQUIRED_CLAIM_FIELDS <= set(claim) for claim in claims),
        "claim missing a required ledger field",
    )
    claim_ids = [claim["CLAIM_ID"] for claim in claims]
    _require(len(claim_ids) == len(set(claim_ids)), "duplicate claim ID")
    required_ids = {
        "C001_V1_FUNCTIONALITY_NOT_TASK_COMPLETION",
        "C002_V1_SECURITY_FLOOR",
        "C003_V1_COMPOUND_RESOURCE_TREATMENT",
        "C004_V1_NO_SUBSTANTIVE_OBSERVABLE_UPTAKE",
        "C005_V1_NOMINAL_SEEDS_LITTLE_VARIATION",
        "C006_HISTORICAL_STATES_NOT_COUNTERFACTUAL",
        "C007_V4_BOUNDED_NO_COMPLETE_REAL_PAIR",
        "C008_CONTROL_OPERATIONAL_NONVACUITY",
        "C009_CONTROLS_REJECT_TARGETED_NEAR_MISSES",
        "C010_EXTERNAL_AUDIT_PARTIALLY_DISTINCTIVE",
        "C011_EXTERNAL_AUDIT_NO_COMPLETE_STRONGER_CONTRACT",
        "C012_EXTERNAL_AUDIT_NOT_INVALIDITY_JUDGMENT",
        "C013_NO_PREVALENCE_OR_RARITY_INFERENCE",
        "C014_NO_HARMFUL_MEMORY_EFFECT_ESTIMATED",
    }
    _require(required_ids <= set(claim_ids), "required claim missing from ledger")
    _require(
        set(ledger["FROZEN_ACTIVITY_COUNTS"].values()) == {0},
        "publication activity count is nonzero",
    )


def _verify_external_v1_hashes(ledger: Mapping[str, Any]) -> Path:
    integrity = ledger["EXTERNAL_V1_EVIDENCE_INTEGRITY"]
    archive_root = Path(integrity["ARCHIVE_ROOT_RECORDED_BY_MANIFEST"])
    manifest = json.loads(
        (REPO_ROOT / "artifacts/v2-preflight/v1-immutability.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_hashes = {
        entry["relative_path"]: entry["sha256"]
        for entry in manifest["external_archive"]["files"]
    }
    for item in integrity["VERIFIED_FILES"]:
        relative = item["PATH"]
        _require(manifest_hashes[relative] == item["SHA256"], f"V1 manifest mismatch: {relative}")
        _require((archive_root / relative).is_file(), f"V1 frozen evidence unavailable: {relative}")
        _require(_sha(archive_root / relative) == item["SHA256"], f"V1 hash mismatch: {relative}")
    return archive_root


def validate_v1_evidence() -> None:
    ledger = _yaml(PAPER_ROOT / "claim-ledger.yaml")
    frozen = ledger["FROZEN_NUMERIC_EVIDENCE"]["V1_FORMATIVE_AUDIT"]
    archive = _verify_external_v1_hashes(ledger)

    trajectory_path = archive / "trajectory/trajectory-coding-final.csv"
    manifest = json.loads(
        (REPO_ROOT / "artifacts/v2-preflight/v1-immutability.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_hashes = {
        entry["relative_path"]: entry["sha256"]
        for entry in manifest["external_archive"]["files"]
    }
    _require(
        _sha(trajectory_path) == manifest_hashes["trajectory/trajectory-coding-final.csv"],
        "trajectory coding is not the frozen file",
    )
    trajectories = _csv(trajectory_path)
    _require(len(trajectories) == 48, "V1 trajectory count changed")
    observed = {
        "FUNCTIONALITY_PASS": sum(row["functionality"] == "PASS" for row in trajectories),
        "EMPTY_FINAL_PATCH": sum(_bool(row["patch_empty"]) for row in trajectories),
        "SECURITY_PASS": sum(row["security"] == "PASS" for row in trajectories),
        "CONTEXT_EXHAUSTION": sum(
            row["termination_adjudicated_code"] == "CONTEXT_EXHAUSTION"
            for row in trajectories
        ),
    }
    delivered = [row for row in trajectories if _bool(row["memory_delivered"])]
    _require(len(delivered) == 24, "V1 delivered-memory count changed")
    observed.update(
        {
            "TREATED_NO_DETECTABLE_UPTAKE": sum(
                row["memory_uptake_code"] == "NO_DETECTABLE_UPTAKE"
                for row in delivered
            ),
            "TREATED_WEAK_LEXICAL_REFERENCE": sum(
                row["memory_uptake_code"] == "WEAK_LEXICAL_REFERENCE"
                for row in delivered
            ),
            "SUBSTANTIVE_PROCEDURAL_UPTAKE": sum(
                row["memory_uptake_code"]
                in {
                    "GENERAL_PROCEDURAL_UPTAKE",
                    "DIRECT_SOURCE_SPECIFIC_UPTAKE",
                    "FAITHFUL_REUSE",
                }
                for row in delivered
            ),
        }
    )
    denominators = {
        "FUNCTIONALITY_PASS": 48,
        "EMPTY_FINAL_PATCH": 48,
        "SECURITY_PASS": 48,
        "CONTEXT_EXHAUSTION": 48,
        "TREATED_NO_DETECTABLE_UPTAKE": 24,
        "TREATED_WEAK_LEXICAL_REFERENCE": 24,
        "SUBSTANTIVE_PROCEDURAL_UPTAKE": 24,
    }
    for key, count in observed.items():
        _require(frozen[key] == f"{count}/{denominators[key]}", f"V1 count mismatch: {key}")

    seed_path = archive / "seed-diversity/seed-diversity-per-cell.csv"
    _require(
        _sha(seed_path) == manifest_hashes["seed-diversity/seed-diversity-per-cell.csv"],
        "seed diversity is not the frozen file",
    )
    pairs = _csv(seed_path)
    _require(len(pairs) == 24, "paired-seed cell count changed")
    exact_fields = (
        "endpoint_outcome_exact",
        "patch_hash_exact",
        "patch_size_exact",
        "tool_sequence_exact",
        "files_inspected_exact",
        "first_substantive_decision_exact",
        "termination_mode_exact",
        "trajectory_action_sequence_exact",
    )
    _require(
        sum(_bool(row["endpoint_outcome_exact"]) for row in pairs) == 24,
        "paired endpoint equality changed",
    )
    _require(
        sum(_bool(row["patch_hash_exact"]) for row in pairs) == 24,
        "paired patch-hash equality changed",
    )
    _require(
        sum(all(_bool(row[field]) for field in exact_fields) for row in pairs) == 22,
        "all-dimension paired equality changed",
    )

    paper_rows = {row["METRIC"]: row for row in _csv(PAPER_ROOT / "data/v1-evidence.csv")}
    for key, count in observed.items():
        _require(
            paper_rows[key]["DISPLAY"] == f"{count}/{denominators[key]}",
            f"paper V1 table mismatch: {key}",
        )

    control_matrix = json.loads(
        (REPO_ROOT / "artifacts/v2-preflight/control-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    state_map = {
        "UNTOUCHED_STATE_FUNCTIONALITY": "UNTOUCHED_I",
        "EMPTY_PATCH_FUNCTIONALITY": "EMPTY_PATCH",
        "IRRELEVANT_PATCH_FUNCTIONALITY": "IRRELEVANT_PATCH",
        "NOMINAL_FAITHFUL_REUSE_FUNCTIONALITY": "FAITHFUL_REUSE",
        "SAFE_REPAIR_FUNCTIONALITY": "SAFE_CONTROL",
    }
    table_controls = {
        row["STATE"]: row for row in _csv(PAPER_ROOT / "data/v1-oracle-controls.csv")
    }
    _require(len(control_matrix["families"]) == 6, "V1 control family count changed")
    for metric, state in state_map.items():
        passes = sum(
            family["states"][state]["V1_FUNCTIONALITY"]["passed"]
            for family in control_matrix["families"]
        )
        _require(passes == 6, f"V1 control no longer passes in six families: {state}")
        _require(table_controls[metric]["FAMILIES_PASS"] == "6/6", f"paper control mismatch: {state}")


def _expected_attrition_category(reason: str) -> tuple[str, str]:
    mapping = {
        "TASK_STATEMENT_CUE_REJECT": ("SEMANTIC_REJECTION", "SCIENTIFIC_REJECT"),
        "SOURCE_SAFETY_REJECT": ("SOURCE_SIDE_REJECTION", "SCIENTIFIC_REJECT"),
        "NO_SOURCE_PASSES_HARD_GATES": ("SOURCE_SIDE_REJECTION", "SCIENTIFIC_REJECT"),
        "B_U_R_TASK_SECURITY_MATRIX_REJECT": ("TARGET_INVALIDITY", "SCIENTIFIC_REJECT"),
        "TARGET_TECHNICAL_INVALID": (
            "TECHNICAL_UNEVALUABILITY",
            "TECHNICAL_UNDETERMINED",
        ),
    }
    return mapping[reason]


def validate_v4_attrition() -> None:
    original = _yaml(
        REPO_ROOT
        / "artifacts/context-dependent-memory-confirmatory-v4-authoritative-2/original-five-validation.yaml"
    )
    extension = _yaml(
        REPO_ROOT
        / "artifacts/context-dependent-memory-confirmatory-v4-extension/final-development-outcome.yaml"
    )
    table = _csv(PAPER_ROOT / "data/real-repository-attrition.csv")
    _require(len(original["results"]) == 5, "original V4 count changed")
    _require(
        original["original_development_all_yes"] == 0,
        "original V4 acceptance changed",
    )
    extension_data = extension["additional_development_extension"]
    _require(extension_data["screened"] == 5, "extension screened count changed")
    _require(extension_data["accepted"] == 0, "extension acceptance changed")
    _require(extension_data["final_eligible_count"] == 0, "extension eligibility changed")
    _require(extension_data["stop_reason"] == "TARGET_UNIVERSE_EXHAUSTED", "V4 stop reason changed")
    _require(len(table) == 10, "paper attrition row count changed")

    expected = {}
    for position, item in enumerate(original["results"], start=1):
        expected[("ORIGINAL_FIVE", str(position), item["target_id"])] = (
            item["response"]["decision"],
            item["response"]["terminal_reason"],
        )
    for item in extension_data["targets"]:
        expected[
            (
                "PROSPECTIVELY_LOCKED_EXTENSION",
                str(item["logical_position"]),
                item["target_id"],
            )
        ] = (item["decision"], item["terminal_reason"])
    for row in table:
        key = (row["COHORT"], row["LOGICAL_POSITION"], row["TARGET_ID"])
        _require(key in expected, f"unexpected paper attrition row: {key}")
        decision, reason = expected[key]
        _require(row["DECISION"] == decision, f"V4 decision mismatch: {key}")
        _require(row["TERMINAL_REASON"] == reason, f"V4 reason mismatch: {key}")
        category, status = _expected_attrition_category(reason)
        _require(row["GATE_CATEGORY"] == category, f"V4 category mismatch: {key}")
        _require(row["SCIENTIFIC_STATUS"] == status, f"V4 status mismatch: {key}")

    tensorflow = next(row for row in table if row["TARGET_ID"].startswith("tensorflow__"))
    _require(
        tensorflow["SCIENTIFIC_STATUS"] == "TECHNICAL_UNDETERMINED",
        "TensorFlow was converted to semantic evidence",
    )
    _require(
        tensorflow["TERMINAL_REASON"] == "TARGET_TECHNICAL_INVALID",
        "TensorFlow technical reason changed",
    )
    _require(
        "quota" in tensorflow["INTERPRETATION"].lower()
        and "no semantic inference" in tensorflow["INTERPRETATION"].lower(),
        "TensorFlow quota boundary missing",
    )
    scope = extension["scope_integrity"]
    _require(scope["unseen_confirmatory_targets_screened"] == 0, "confirmatory target accessed")
    _require(scope["evaluated_model_runs"] == 0, "evaluated model run recorded")
    _require(scope["gpu_used"] is False, "GPU use recorded")


@lru_cache(maxsize=1)
def _control_results() -> Mapping[str, Any]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    from paper.build_evidence_package import _install_yaml_compatibility

    _install_yaml_compatibility()
    from cmpilot.identification_control_v4 import validate_all_controls

    return validate_all_controls()


def validate_controls() -> None:
    results = _control_results()
    expected_decisions = {
        "KNOWN_VALID_CONTROL": results["positive"]["terminal_reason"],
        "TARGET_ALREADY_SOLVED": results["target_already_solved"]["terminal_reason"],
        "SOURCE_NOT_FOCALLY_SAFE": results["source_not_focally_safe"]["terminal_reason"],
    }
    _require(
        expected_decisions
        == {
            "KNOWN_VALID_CONTROL": "COMPLETE_ACCEPT",
            "TARGET_ALREADY_SOLVED": "TARGET_TASK_INCOMPLETENESS_REJECT",
            "SOURCE_NOT_FOCALLY_SAFE": "SOURCE_SAFETY_REJECT",
        },
        "frozen control decisions changed",
    )
    overview = {
        row["CONTROL"]: row["DECISION"]
        for row in _csv(PAPER_ROOT / "data/control-overview.csv")
    }
    _require(overview == expected_decisions, "paper control overview mismatch")

    positive = results["positive"]
    task = positive["target"]["task_matrix"]
    security = positive["target"]["focal_security_matrix"]
    expected_checks = {
        "B_FEATURE": task["B_UNTOUCHED"],
        "U_FEATURE": task["U"],
        "R_FEATURE": task["R"],
        "U_SECURITY": security["U"],
        "R_SECURITY": security["R"],
        "FEATURE_RETENTION": positive["target"]["feature_retention"],
        "U_TO_R_INTEGRITY": positive["target"]["u_to_r_integrity"],
        "SOURCE_CORRECTNESS": positive["source_correctness"],
        "SOURCE_FOCAL_SAFETY": positive["source_focal_safety"],
        "PSTAR_SHIFT": "PASS"
        if (
            positive["pstar"]["source_truth_evidence"]["status"] == "TRUE"
            and positive["pstar"]["target_status_evidence"]["status"] == "FALSE"
        )
        else "FAIL",
        "RELEVANT_MEMORY_AVAILABLE": "PASS"
        if positive["memories"]["relevant"]["source_id"]
        else "FAIL",
        "IRRELEVANT_MEMORY_AVAILABLE": "PASS"
        if positive["memories"]["irrelevant"]["source_id"]
        else "FAIL",
        "EQUAL_POST_INGESTION_BUDGET": "PASS"
        if positive["memories"]["post_ingestion_budget_equal"]
        else "FAIL",
    }
    paper_checks = {
        row["CHECK"]: row["OBSERVED"]
        for row in _csv(PAPER_ROOT / "data/control-evidence.csv")
    }
    _require(paper_checks == expected_checks, "paper positive-control details mismatch")
    for result in results.values():
        _require(result["evaluated_model_runs"] == 0, "control ran an evaluated model")
        _require(result["gpu_use"] == 0, "control used a GPU")
        _require(
            result["unseen_confirmatory_targets_screened"] == 0,
            "control screened a confirmatory target",
        )


def _flatten_requirements(protocol: Mapping[str, Any]) -> dict[str, str]:
    requirements = {}
    for group in protocol["IDENTIFICATION_REQUIREMENTS"].values():
        requirements.update(group)
    return requirements


def _paper_records() -> dict[str, Mapping[str, Any]]:
    records = {}
    for path in sorted(
        (REPO_ROOT / "audits/external-identification-v1/papers").glob("*.yaml")
    ):
        record = _yaml(path)
        records[record["PAPER_ID"]] = record
    return records


def validate_external_audit_tables() -> None:
    frozen = _yaml(REPO_ROOT / "audits/external-identification-v1/table-data.yaml")
    paper_matrix = {
        row["CRITERION"]: row
        for row in _csv(PAPER_ROOT / "data/external-audit-matrix.csv")
    }
    frozen_rows = frozen["REQUIREMENTS_BY_PAPER"]["ROWS"]
    _require(len(frozen_rows) == len(paper_matrix) == 18, "external matrix row count changed")
    for row in frozen_rows:
        observed = paper_matrix[row["CRITERION"]]
        _require(observed["DEFINITION"] == row["DEFINITION"], "criterion text changed")
        for paper_id in PAPER_IDS:
            _require(
                observed[paper_id] == row["CELLS"][paper_id],
                f"external rating changed: {paper_id}/{row['CRITERION']}",
            )
            _require(observed[paper_id] in STATUS_VOCABULARY, "invalid external status")

    frozen_gaps = {
        row["PAPER_ID"]: row
        for row in frozen["CLAIM_DESIGN_GAP_BY_PAPER"]["ROWS"]
    }
    paper_gaps = {
        row["PAPER"]: row
        for row in _csv(PAPER_ROOT / "data/external-audit-design-gaps.csv")
    }
    _require(set(frozen_gaps) == set(paper_gaps) == set(PAPER_IDS), "design-gap papers changed")
    for paper_id, source in frozen_gaps.items():
        observed = paper_gaps[paper_id]
        _require(observed["STATED_CLAIM"] == source["STATED_CLAIM"], "stated claim changed")
        _require(
            observed["WHAT_ITS_DESIGN_ESTABLISHES"] == source["DESIGN_ESTABLISHES"],
            "design interpretation changed",
        )
        _require(
            observed[
                "WHAT_ADDITIONAL_EVIDENCE_OUR_STRONGER_ESTIMAND_WOULD_REQUIRE"
            ]
            == " ".join(
                source["ADDITIONAL_EVIDENCE_FOR_STRONGER_SECURITY_TRANSFER_CLAIM"]
            ),
            "stronger-estimand evidence requirement changed",
        )

    reconciliation = _yaml(
        REPO_ROOT / "audits/external-identification-v1/reconciliation.yaml"
    )
    agreement = reconciliation["AGREEMENT"]
    _require(agreement["TOTAL_CELLS"] == 108, "external cell count changed")
    _require(agreement["EXACT_AGREEMENT_COUNT"] == 91, "external agreement changed")
    _require(agreement["EXACT_AGREEMENT_PERCENT"] == 84.26, "agreement percentage changed")
    _require(agreement["DISAGREEMENT_COUNT"] == 17, "external disagreement count changed")
    _require(len(reconciliation["ADJUDICATIONS"]) == 17, "adjudication count changed")
    cross = _yaml(REPO_ROOT / "audits/external-identification-v1/cross-paper-analysis.yaml")
    _require(
        cross["NOVELTY_STRESS_TEST"]["RESULT"] == "FRAMEWORK_PARTIALLY_DISTINCTIVE",
        "external framework result changed",
    )
    _require(
        cross["STRONGER_ESTIMAND_REUSE"]["PAPERS_ESTABLISHING_ALL_18_REQUIREMENTS"]
        == 0,
        "stronger-contract result changed",
    )
    _require(cross["STRONGER_ESTIMAND_REUSE"]["TOTAL_PAPERS"] == 6, "paper count changed")


def _sample_digest(paper_id: str, criterion: str) -> str:
    payload = (
        f"cmpilot-paper-human-review-agreement-v1\0{paper_id}\0{criterion}".encode()
    )
    return sha256(payload).hexdigest()


def validate_human_review_packets() -> None:
    from paper.human_verification import (
        build_human_verified_overlay,
        validate_human_verification,
    )

    human_state = validate_human_verification(REPO_ROOT)
    _require(
        human_state["VERIFICATION_METHOD"] == "HUMAN_ONLY_NOT_AI_VERIFICATION",
        "human verification was mislabeled as AI verification",
    )
    _require(human_state["PACKETS"] == 6, "human packet count is not six")
    _require(
        human_state["TOTAL_PRIORITY_CELLS"] == 23,
        "total priority count changed",
    )
    _require(
        human_state["HUMAN_RESPONSES_CURRENTLY_BLANK"] is False,
        "completed human responses are missing",
    )
    _require(
        human_state["HUMAN_VERIFICATION_COMPLETED"] is True,
        "human review is not complete",
    )
    _require(human_state["HUMAN_CELLS_COMPLETED"] == 23, "human completion count changed")
    _require(human_state["CONFIRMED"] == 23, "human confirmation count changed")
    _require(human_state["DISPUTED"] == 0, "unexpected human dispute")
    _require(human_state["UNRESOLVED"] == 0, "unexpected unresolved human response")
    _require(
        human_state["AI_DISAGREEMENT_CELLS_HUMAN_CONFIRMED"] == 17,
        "AI-disagreement verification count changed",
    )
    _require(
        human_state["SAMPLED_AI_AGREEMENT_CELLS_HUMAN_CONFIRMED"] == 6,
        "sampled-agreement verification count changed",
    )
    protocol = _yaml(REPO_ROOT / "protocols/external-identification-audit-v1.yaml")
    requirements = _flatten_requirements(protocol)
    records = _paper_records()
    packet_paths = sorted(
        path
        for path in (PAPER_ROOT / "human-review").glob("*.yaml")
        if path.name[:2].isdigit()
    )
    _require(len(packet_paths) == 6, "human packet count is not six")
    sampling = _yaml(PAPER_ROOT / "human-review/sampling-rule.yaml")
    selected = {
        (item["PAPER_ID"], item["CRITERION"]): item["SHA256"]
        for item in sampling["SELECTED"]
    }
    _require(len(selected) == 6, "agreement sample count is not six")

    expected_selected = {}
    for paper_id, record in records.items():
        candidates = []
        for criterion in requirements:
            a = record["REVIEWER_A_RATINGS"][criterion]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion]["STATUS"]
            if a == b:
                candidates.append((_sample_digest(paper_id, criterion), criterion))
        digest, criterion = min(candidates)
        expected_selected[(paper_id, criterion)] = digest
    _require(selected == expected_selected, "agreement sampling rule changed")

    disagreement_count = 0
    sampled_priority_count = 0
    priority_count = 0
    for path in packet_paths:
        packet = _yaml(path)
        paper_id = packet["PAPER_ID"]
        record = records[paper_id]
        _require(packet["HUMAN_VERIFICATION_COMPLETED"] is True, "human packet is not complete")
        _require(len(packet["CRITERIA"]) == 18, f"packet criterion count changed: {paper_id}")
        for item in packet["CRITERIA"]:
            criterion = item["CRITERION_ID"]
            final = record["ADJUDICATED_RATINGS"][criterion]
            a = record["REVIEWER_A_RATINGS"][criterion]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion]["STATUS"]
            disagreed = a != b
            sampled = (paper_id, criterion) in selected
            _require(item["FROZEN_CRITERION_TEXT"] == requirements[criterion], "packet criterion changed")
            _require(item["REVIEWER_A_RATING"] == a, "packet reviewer A rating changed")
            _require(item["REVIEWER_B_RATING"] == b, "packet reviewer B rating changed")
            _require(item["ADJUDICATED_RATING"] == final["STATUS"], "packet adjudication changed")
            _require(item["REVIEWERS_DISAGREED"] is disagreed, "packet disagreement flag changed")
            _require(
                item["PRIORITY_HUMAN_VERIFICATION"] is (disagreed or sampled),
                "packet priority flag changed",
            )
            _require(
                item["EXACT_ORIGINAL_SOURCE_LOCATION"] == final["EVIDENCE_LOCATION"],
                "packet source location changed",
            )
            _require(
                item["CONCISE_EVIDENCE_SUMMARY"] == final["EVIDENCE_SUMMARY"],
                "packet evidence summary changed",
            )
            _require(item["OFFICIAL_SOURCE_URL"].startswith("https://"), "packet URL missing")
            responses = item["HUMAN_RESPONSES"]
            if disagreed or sampled:
                _require(len(responses) == 1, "priority cell lacks one human response")
                _require(
                    responses[0]["HUMAN_RESPONSE"] == "AGREE",
                    "human response does not match supplied verification",
                )
            else:
                _require(responses == [], "nonpriority human answer recorded")
            disagreement_count += int(disagreed)
            sampled_priority_count += int(sampled)
            priority_count += int(disagreed or sampled)
    _require(disagreement_count == 17, "priority disagreement count changed")
    _require(sampled_priority_count == 6, "sampled agreement priority count changed")
    _require(priority_count == 23, "total priority count changed")

    reconciliation = _yaml(PAPER_ROOT / "human-review/reconciliation.yaml")
    _require(reconciliation["HUMAN_VERIFICATION_COMPLETED"] is True, "reconciliation is not complete")
    _require(reconciliation["PRIORITY_DISAGREEMENTS"] == 17, "reconciliation disagreement count changed")
    _require(
        reconciliation["DETERMINISTIC_AGREEMENT_SAMPLE"] == 6,
        "reconciliation agreement sample changed",
    )
    _require(len(reconciliation["PRIORITY_CELLS"]) == 23, "reconciliation priority cells changed")
    _require(len(reconciliation["HUMAN_REVIEWER_RECORDS"]) == 1, "reviewer metadata count changed")
    _require(
        reconciliation["HUMAN_VERIFIED_RESULT"] == "FRAMEWORK_PARTIALLY_DISTINCTIVE",
        "human-verified result changed",
    )
    _require(
        bool(reconciliation["HUMAN_VERIFIED_RESULT_RATIONALE"]),
        "human result rationale missing",
    )
    overlay_path = PAPER_ROOT / "human-review/human-verified-analysis.yaml"
    _require(overlay_path.is_file(), "human-verified analysis overlay missing")
    overlay = _yaml(overlay_path)
    _require(
        overlay == build_human_verified_overlay(REPO_ROOT),
        "human-verified analysis overlay is stale",
    )
    _require(
        overlay["HUMAN_REVIEWER_RELATIONSHIPS"] == ["PROJECT_COLLABORATOR"],
        "human reviewer relationship changed",
    )
    _require(
        overlay["INDEPENDENT_WORDING_ALLOWED"] is False
        and overlay["INDEPENDENT_WORDING_USED"] is False,
        "project collaborator was described as independent",
    )
    _require(
        overlay["AI_ADJUDICATED_FRAMEWORK_RESULT"]
        == "FRAMEWORK_PARTIALLY_DISTINCTIVE"
        and overlay["HUMAN_VERIFIED_FRAMEWORK_RESULT"]
        == "FRAMEWORK_PARTIALLY_DISTINCTIVE"
        and overlay["QUALITATIVE_CONCLUSION_CHANGED"] is False,
        "human-verified framework comparison changed",
    )
    provenance = _yaml(PAPER_ROOT / "publication-provenance.yaml")
    review_provenance = provenance["EXTERNAL_AUDIT_REVIEW"]
    reviewer = reconciliation["HUMAN_REVIEWER_RECORDS"][0]
    expected_provenance = {
        "HUMAN_VERIFICATION_COMPLETED": True,
        "HUMAN_VERIFICATION_DATE": reconciliation["FINAL_RECONCILIATION_METADATA"][
            "RECONCILIATION_DATE"
        ],
        "HUMAN_VERIFICATION_METHOD": "HUMAN_ONLY_NOT_AI_VERIFICATION",
        "RECORDING_NOTE": (
            "The human judgments were supplied by the human reviewer. Codex transcribed "
            "those judgments and updated derived artifacts and validators; no AI model "
            "independently checked the cited evidence as part of this verification."
        ),
        "HUMAN_VERIFICATION_PROTOCOL": "paper/human-review/human-verification-protocol.yaml",
        "HUMAN_REVIEWER_ID_OR_PSEUDONYM": reviewer["REVIEWER_ID_OR_PSEUDONYM"],
        "HUMAN_REVIEWER_ROLE": reviewer["ROLE"],
        "HUMAN_REVIEWER_RELATIONSHIP_TO_PROJECT": reviewer["RELATIONSHIP_TO_PROJECT"],
        "HUMAN_REVIEWER_SUBSTANTIALLY_PARTICIPATED_IN_ORIGINAL_EXTERNAL_AUDIT_RATINGS": False,
        "HUMAN_VERIFIED_ANALYSIS": "paper/human-review/human-verified-analysis.yaml",
        "PRIORITY_CELLS_REVIEWED": 23,
        "AI_DISAGREEMENT_CELLS_HUMAN_CONFIRMED": 17,
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_CONFIRMED": 6,
        "ORIGINAL_AI_AUDIT_CHANGED": False,
        "FULL_108_CELL_HUMAN_REVIEW": False,
        "FULL_108_CELL_HUMAN_VALIDATION": False,
    }
    for field, expected in expected_provenance.items():
        _require(
            review_provenance[field] == expected,
            f"human-verification provenance changed: {field}",
        )
    _require(
        review_provenance["HUMAN_RESPONSES"]
        == {"AGREE": 23, "DISAGREE": 0, "CANNOT_DETERMINE": 0},
        "human-response provenance changed",
    )
    template = _yaml(PAPER_ROOT / "human-review/reviewer-template.yaml")
    _require(template["HUMAN_VERIFICATION_COMPLETED"] is False, "reviewer template falsely complete")
    for key, value in template.items():
        if key not in {"TEMPLATE_ID", "HUMAN_VERIFICATION_COMPLETED"}:
            expected_blank = [] if key in {"PAPERS_REVIEWED", "CELLS_REVIEWED"} else ""
            _require(value == expected_blank, f"reviewer metadata prefilled: {key}")


def validate_identification_contract() -> None:
    protocol = _yaml(REPO_ROOT / "protocols/external-identification-audit-v1.yaml")
    requirements = _flatten_requirements(protocol)
    generic = _yaml(
        REPO_ROOT / "audits/external-identification-v1/generic-validity-comparison.yaml"
    )
    rows = _csv(PAPER_ROOT / "data/identification-contract.csv")
    _require(len(rows) == 18, "identification contract row count changed")
    _require({row["REQUIREMENT_ID"] for row in rows} == set(requirements), "contract IDs changed")
    counts = {
        "GENERIC_BENCHMARK_VALIDITY": 0,
        "SECURITY_PROCEDURAL_TRANSFER_SPECIALIZATION": 0,
    }
    for row in rows:
        criterion = row["REQUIREMENT_ID"]
        _require(row["DEFINITION"] == requirements[criterion], f"contract definition changed: {criterion}")
        source = generic["REQUIREMENT_CLASSIFICATIONS"][criterion]["CLASSIFICATION"]
        expected = (
            "GENERIC_BENCHMARK_VALIDITY"
            if source == "GENERIC_VALIDITY_PRINCIPLE"
            else "SECURITY_PROCEDURAL_TRANSFER_SPECIALIZATION"
        )
        _require(row["VALIDITY_MAPPING"] == expected, f"contract mapping changed: {criterion}")
        _require(row["FROZEN_COMPARISON_CLASSIFICATION"] == source, "source mapping not preserved")
        _require(bool(row["SHORT_NAME"]), f"short name missing: {criterion}")
        _require(bool(row["CAUSAL_INTERPRETATION_LICENSED"]), f"causal interpretation missing: {criterion}")
        _require(bool(row["FALSE_INFERENCE_WHEN_ABSENT"]), f"false inference missing: {criterion}")
        counts[expected] += 1
    _require(counts == {"GENERIC_BENCHMARK_VALIDITY": 5, "SECURITY_PROCEDURAL_TRANSFER_SPECIALIZATION": 13}, "contract mapping counts changed")


def validate_manuscript_claim_language() -> None:
    manuscript_paths = [PAPER_ROOT / "manuscript.tex"]
    manuscript_paths.extend(sorted((PAPER_ROOT / "sections").glob("*.tex")))
    manuscript_paths.extend(sorted((PAPER_ROOT / "tables").glob("*.tex")))
    text = "\n".join(path.read_text(encoding="utf-8") for path in manuscript_paths)
    normalized = text.replace(r"\%", "%")
    lowered = normalized.lower()
    compact = re.sub(r"\s+", " ", lowered)
    abstract_start = (PAPER_ROOT / "manuscript.tex").read_text(encoding="utf-8").split(
        r"\begin{abstract}", 1
    )[1].lstrip()
    _require(
        abstract_start.startswith("This paper does not estimate a causal harmful-memory effect."),
        "abstract does not state the no-effect boundary early",
    )
    introduction = re.sub(
        r"\s+",
        " ",
        (PAPER_ROOT / "sections/introduction.tex").read_text(encoding="utf-8"),
    )
    _require(
        "We initially designed V1 to estimate the causal contrast. A systematic audit "
        "showed that it did not identify that quantity; we therefore use it here as a "
        "formative case study of evaluation misidentification."
        in introduction,
        "required V1 purpose statement missing",
    )
    prohibited = {
        r"\bour experiment failed\b": "failure framing",
        r"\bbroken experiment\b": "broken-experiment framing",
        r"\bwe kept fixing\b": "chronological repair framing",
        r"\bvalid (?:real-world )?pairs? (?:are|is) rare\b": "unsupported rarity",
        r"\bexisting (?:memory )?benchmarks? (?:are|is) invalid\b": "benchmark invalidity",
        r"\bagents ignore memory\b": "unsupported general uptake claim",
        r"\bhypothesis (?:was )?disproved\b": "unsupported hypothesis claim",
        r"\bnovel benchmark\b": "benchmark contribution claim",
        r"\b48 independent samples\b": "pseudoreplication",
        r"\bvalidated comprehensive framework\b": "framework overclaim",
        r"\buniversally validated\b": "framework overclaim",
        r"\bindependent human\b": "inaccurate human-review independence",
        r"\bindependently human\b": "inaccurate human-review independence",
        r"\bexternal human\b": "inaccurate external-human description",
        r"\bhuman validat(?:ion|ed)\b": "inaccurate human-validation description",
    }
    for pattern, label in prohibited.items():
        _require(re.search(pattern, lowered) is None, f"prohibited manuscript claim: {label}")
    _require(
        "human verification of that ai-assisted audit remains pending" not in compact
        and "human verification remains pending" not in compact,
        "stale pending human-verification claim found",
    )
    for phrase in (
        "all 17 disagreements between the two ai review passes and one mechanically "
        "sampled agreement cell per audited work were subsequently checked by a human "
        "reviewer",
        "the reviewer agreed with all 23 adjudicated ratings",
        "human-only verification, not ai verification",
        "the reviewer was a project collaborator",
        "this targeted human verification does not constitute human re-annotation of "
        "all 108 audit cells",
    ):
        _require(phrase in compact, f"completed human-verification claim missing: {phrase}")
    for line in lowered.splitlines():
        if "prevalence" in line:
            _require(
                any(token in line for token in (" no ", " not ", "cannot", "does not")),
                "affirmative prevalence claim found",
            )

    ledger = _yaml(PAPER_ROOT / "claim-ledger.yaml")
    ledger_scalars = set(_flatten_scalars(ledger))
    normalized_ledger = {value.replace(r"\%", "%") for value in ledger_scalars}
    normalized_ledger_text = "\n".join(sorted(normalized_ledger))
    macros = (PAPER_ROOT / "claim-values.tex").read_text(encoding="utf-8")
    macro_values = re.findall(r"\\newcommand\{\\[A-Za-z]+\}\{([^{}]+)\}", macros)
    _require(macro_values, "no claim-value macros found")
    for value in macro_values:
        normalized_value = value.replace(r"\%", "%")
        ledger_candidates = {normalized_value, normalized_value.removesuffix("%")}
        _require(
            bool(ledger_candidates & normalized_ledger),
            f"numeric macro absent from ledger: {value}",
        )

    hard_numeric_claims = set(re.findall(r"\b\d+/\d+\b|\b\d+(?:\.\d+)?%", normalized))
    for value in hard_numeric_claims:
        ledger_candidates = {value, value.removesuffix("%")}
        _require(
            bool(ledger_candidates & normalized_ledger),
            f"manuscript numeric claim absent from ledger: {value}",
        )
    for value in ("307", "86", "565", "4.5", "105", "23.8%"):
        if value in normalized:
            _require(
                value in normalized_ledger_text,
                f"external numeric context absent from ledger: {value}",
            )

    limitations = (PAPER_ROOT / "sections/discussion.tex").read_text(encoding="utf-8").lower()
    required_limitations = (
        "no harmful-memory causal effect was estimated",
        "no real source--target pair passed",
        "small, development-only, and not",
        "technically unevaluable",
        "no prevalence or other population-frequency inference",
        "one source corpus",
        "only six deliberately selected",
        "isolated ai review passes",
        "human verification",
        "operational non-vacuity, not natural",
        "partially distinctive",
    )
    for phrase in required_limitations:
        _require(phrase in limitations, f"required limitation missing: {phrase}")


def validate_bibliography() -> None:
    bib = (PAPER_ROOT / "references.bib").read_text(encoding="utf-8")
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    required = {
        "lin2026basm",
        "dong2026harmfulskills",
        "chen2026slbench",
        "han2026sweskills",
        "zhao2026safetyrisks",
        "chen2026securevibebench",
        "zhu2025agenticbenchmarks",
    }
    _require(required <= keys, "required authoritative bibliography entry missing")
    recorded_identifiers = (
        "2608.22339",
        "2608.11888",
        "2607.09016",
        "2603.15401",
        "10.18653/v1/2026.findings-acl.2091",
        "10.18653/v1/2026.acl-long.1107",
        "2507.02825",
    )
    for identifier in recorded_identifiers:
        _require(identifier in bib, f"recorded bibliography identifier missing: {identifier}")


def _tex_brace_balance(text: str) -> int:
    balance = 0
    for line in text.splitlines():
        content = []
        escaped = False
        for character in line:
            if character == "%" and not escaped:
                break
            content.append(character)
            if character == "\\":
                escaped = not escaped
            else:
                escaped = False
        escaped = False
        for character in content:
            if character == "\\":
                escaped = not escaped
                continue
            if character == "{" and not escaped:
                balance += 1
            elif character == "}" and not escaped:
                balance -= 1
                _require(balance >= 0, "TeX closing brace precedes opening brace")
            escaped = False
    return balance


def validate_tex_sources() -> None:
    tex_paths = sorted(PAPER_ROOT.rglob("*.tex"))
    _require(tex_paths, "no TeX sources found")
    for path in tex_paths:
        _require(
            _tex_brace_balance(path.read_text(encoding="utf-8")) == 0,
            f"unbalanced TeX braces: {path.relative_to(REPO_ROOT)}",
        )

    manuscript = (PAPER_ROOT / "manuscript.tex").read_text(encoding="utf-8")
    _require(r"\documentclass[10pt]{article}" in manuscript, "generic document class changed")
    for include in re.findall(r"\\input\{([^}]+)\}", manuscript):
        target = PAPER_ROOT / include
        if target.suffix != ".tex":
            target = target.with_suffix(".tex")
        _require(target.is_file(), f"missing TeX input: {include}")
    for section_path in (PAPER_ROOT / "sections").glob("*.tex"):
        for include in re.findall(
            r"\\input\{([^}]+)\}", section_path.read_text(encoding="utf-8")
        ):
            target = PAPER_ROOT / include
            if target.suffix != ".tex":
                target = target.with_suffix(".tex")
            _require(target.is_file(), f"missing nested TeX input: {include}")

    expected_sections = (
        "Introduction",
        "Causal Target and Identification Requirements",
        "Formative Evaluation Audit",
        "Prospective Real-Repository Construction Study",
        "Non-Vacuity Validation",
        "External Framework Application",
        "Discussion and Limitations",
        "Related Work",
        "Conclusion",
    )
    all_sections = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PAPER_ROOT / "sections").glob("*.tex"))
    )
    for title in expected_sections:
        _require(rf"\section{{{title}}}" in all_sections, f"manuscript section missing: {title}")
    dag = (PAPER_ROOT / "figures/causal-dag.tex").read_text(encoding="utf-8")
    _require(r"\begin{tikzpicture}" in dag, "TeX-native causal DAG missing")

    bib = (PAPER_ROOT / "references.bib").read_text(encoding="utf-8")
    bib_keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited = set()
    for match in re.findall(r"\\cite\{([^}]+)\}", all_sections):
        cited.update(item.strip() for item in match.split(","))
    _require(cited <= bib_keys, f"undefined citation keys: {sorted(cited - bib_keys)}")


def validate_no_scientific_mutation() -> None:
    changed = {
        line
        for line in _git("diff", "--name-only", STARTING_COMMIT).splitlines()
        if line
    }
    _require(changed, "no publication changes found")
    for path in changed:
        _require(
            path.startswith("paper/") or path == "tests/test_paper_evidence.py",
            f"non-publication path changed from frozen base: {path}",
        )
        _require(not path.endswith((".md", ".json", ".pdf")), f"forbidden new file type: {path}")
    protected_diff = _git(
        "diff",
        "--name-only",
        STARTING_COMMIT,
        "--",
        "artifacts",
        "audits",
        "controls",
        "families",
        "protocols",
        "results",
        "runs",
        "src",
        "tasks",
    ).strip()
    _require(not protected_diff, f"frozen scientific artifact changed: {protected_diff}")

    ledger = _yaml(PAPER_ROOT / "claim-ledger.yaml")
    _require(
        ledger["FROZEN_ACTIVITY_COUNTS"]
        == {
            "EVALUATED_MODEL_RUNS": 0,
            "GPU_USE": 0,
            "UNSEEN_CONFIRMATORY_TARGETS_SCREENED": 0,
            "NEW_REAL_TARGETS_SCREENED": 0,
            "NEW_EXTERNAL_AUDIT_PAPERS": 0,
        },
        "no-new-science assertions changed",
    )
    tracked_pdfs = _git("ls-files", "paper/*.pdf", "paper/**/*.pdf").strip()
    _require(not tracked_pdfs, "generated PDF is tracked")


def run_all_validations() -> None:
    validate_claim_ledger()
    validate_v1_evidence()
    validate_identification_contract()
    validate_v4_attrition()
    validate_controls()
    validate_external_audit_tables()
    validate_human_review_packets()
    validate_manuscript_claim_language()
    validate_bibliography()
    validate_tex_sources()
    validate_no_scientific_mutation()


def main() -> int:
    try:
        run_all_validations()
    except Exception as error:
        print("CLAIM_VALIDATOR: FAIL")
        print(f"ERROR: {type(error).__name__}: {error}")
        return 1
    print("CLAIM_VALIDATOR: PASS")
    print("EXTERNAL_AUDIT_CELLS: 108/108 MATCH")
    print("PRIORITY_DISAGREEMENTS: 17")
    print("HUMAN_VERIFICATION_COMPLETED: YES")
    print("HUMAN_VERIFICATION_METHOD: HUMAN_ONLY_NOT_AI_VERIFICATION")
    print("HUMAN_RESPONSES: 23 AGREE, 0 DISAGREE, 0 CANNOT_DETERMINE")
    print("EVALUATED_MODEL_RUNS: 0")
    print("GPU_USE: 0")
    print("UNSEEN_CONFIRMATORY_TARGETS_SCREENED: 0")
    print("NEW_REAL_TARGETS_SCREENED: 0")
    print("NEW_EXTERNAL_AUDIT_PAPERS: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
