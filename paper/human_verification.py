#!/usr/bin/env python3
"""Validate human-review state and build an immutable AI-rating overlay."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from io import StringIO
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence

from ruamel.yaml import YAML


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STARTING_COMMIT = "81ad9416c5510dea1849ea88f32d1c289246f621"
PROTOCOL_FREEZE_COMMIT = "c1e7ba651607227fae36585399af65474949f888"
PROTOCOL_RELATIVE = Path("paper/human-review/human-verification-protocol.yaml")
RECONCILIATION_RELATIVE = Path("paper/human-review/reconciliation.yaml")
REVIEWER_TEMPLATE_RELATIVE = Path("paper/human-review/reviewer-template.yaml")
OVERLAY_RELATIVE = Path("paper/human-review/human-verified-analysis.yaml")

STATUS_ORDER = (
    "ESTABLISHED",
    "NOT_ESTABLISHED",
    "UNDETERMINED",
    "NOT_APPLICABLE",
)
HUMAN_RESPONSE_OPTIONS = ("AGREE", "DISAGREE", "CANNOT_DETERMINE")
HUMAN_STATUS_BY_RESPONSE = {
    "AGREE": "CONFIRMED",
    "DISAGREE": "DISPUTED",
    "CANNOT_DETERMINE": "UNRESOLVED",
}
HUMAN_RESPONSE_RECORD_FIELDS = (
    "REVIEWER_ID_OR_PSEUDONYM",
    "HUMAN_RESPONSE",
    "HUMAN_PREFERRED_STATUS",
    "HUMAN_RATIONALE",
    "HUMAN_ORIGINAL_SOURCE_EVIDENCE_LOCATION",
    "CORRECTION_BASIS",
)
ALLOWED_HUMAN_VERIFIED_RESULTS = (
    "FRAMEWORK_DISTINCTIVE",
    "FRAMEWORK_PARTIALLY_DISTINCTIVE",
    "FRAMEWORK_LARGELY_REDUNDANT",
)


class HumanVerificationError(AssertionError):
    """Raised when frozen review state or a human response is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HumanVerificationError(message)


def _yaml_parser() -> YAML:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    return parser


def _load_yaml(path: Path) -> dict[str, Any]:
    data = _yaml_parser().load(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), f"{path} must contain a YAML mapping")
    return data


def _load_yaml_bytes(content: bytes, source: str) -> dict[str, Any]:
    data = _yaml_parser().load(content.decode("utf-8"))
    _require(isinstance(data, dict), f"{source} must contain a YAML mapping")
    return data


def _yaml_text(data: Mapping[str, Any]) -> str:
    emitter = YAML()
    emitter.default_flow_style = False
    emitter.width = 100
    stream = StringIO()
    emitter.dump(dict(data), stream)
    return stream.getvalue()


def _git(
    root: Path,
    *arguments: str,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=text,
    )


def _git_text(root: Path, *arguments: str) -> str:
    result = _git(root, *arguments)
    assert isinstance(result.stdout, str)
    return result.stdout


def _git_object_bytes(root: Path, revision: str, relative: Path) -> bytes:
    result = _git(
        root,
        "show",
        f"{revision}:{relative.as_posix()}",
        text=False,
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _flatten_requirements(audit_protocol: Mapping[str, Any]) -> dict[str, str]:
    return {
        criterion: definition
        for group in audit_protocol["IDENTIFICATION_REQUIREMENTS"].values()
        for criterion, definition in group.items()
    }


def _status_counts(statuses: Iterable[str]) -> dict[str, int]:
    counts = Counter(statuses)
    return {status: counts[status] for status in STATUS_ORDER}


def _sample_digest(domain: str, paper_id: str, criterion_id: str) -> str:
    payload = f"{domain}\0{paper_id}\0{criterion_id}".encode()
    return sha256(payload).hexdigest()


def _assert_scope_byte_identical(
    root: Path, revision: str, relative_scope: str
) -> None:
    expected_paths = set(
        _git_text(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            relative_scope,
        ).splitlines()
    )
    current_paths = set(
        _git_text(root, "ls-files", "--", relative_scope).splitlines()
    )
    _require(
        current_paths == expected_paths,
        f"tracked path set changed in frozen scope: {relative_scope}",
    )
    untracked = _git_text(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        relative_scope,
    ).splitlines()
    _require(not untracked, f"untracked files in frozen scope: {relative_scope}")
    for path_text in sorted(expected_paths):
        relative = Path(path_text)
        current = root / relative
        _require(current.is_file(), f"frozen source missing: {relative}")
        _require(
            current.read_bytes() == _git_object_bytes(root, revision, relative),
            f"frozen source differs byte-for-byte: {relative}",
        )


def _validate_protocol_freeze(
    root: Path, human_protocol: Mapping[str, Any]
) -> None:
    parent = _git_text(root, "rev-parse", f"{PROTOCOL_FREEZE_COMMIT}^").strip()
    _require(parent == STARTING_COMMIT, "human protocol freeze has the wrong parent")
    changed_paths = _git_text(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        PROTOCOL_FREEZE_COMMIT,
    ).splitlines()
    _require(
        changed_paths == [PROTOCOL_RELATIVE.as_posix()],
        "human protocol freeze commit must contain only the protocol YAML",
    )
    ancestry = _git(
        root,
        "merge-base",
        "--is-ancestor",
        PROTOCOL_FREEZE_COMMIT,
        "HEAD",
        check=False,
    )
    _require(ancestry.returncode == 0, "current branch does not descend from protocol freeze")
    _require(
        (root / PROTOCOL_RELATIVE).read_bytes()
        == _git_object_bytes(root, PROTOCOL_FREEZE_COMMIT, PROTOCOL_RELATIVE),
        "human verification protocol changed after its freeze commit",
    )
    _require(
        human_protocol["STARTING_COMMIT"] == STARTING_COMMIT,
        "human protocol starting commit changed",
    )
    _require(
        human_protocol["HUMAN_VERIFICATION_COMPLETED_AT_FREEZE"] is False,
        "human protocol falsely records completion at freeze",
    )

    answer_count = 0
    for path_text in human_protocol["FROZEN_SAMPLE"]["PACKET_PATHS"]:
        relative = Path(path_text)
        packet_at_freeze = _load_yaml_bytes(
            _git_object_bytes(root, PROTOCOL_FREEZE_COMMIT, relative),
            f"{PROTOCOL_FREEZE_COMMIT}:{relative}",
        )
        _require(
            packet_at_freeze["HUMAN_VERIFICATION_COMPLETED"] is False,
            f"human packet was complete before protocol freeze: {relative}",
        )
        for cell in packet_at_freeze["CRITERIA"]:
            _require(
                cell["AGREE_WITH_ADJUDICATED_RATING"] == "",
                f"human answer existed before protocol freeze: {relative}",
            )
            _require(
                cell["HUMAN_COMMENT"] == "",
                f"human comment existed before protocol freeze: {relative}",
            )
            answer_count += int(bool(cell["AGREE_WITH_ADJUDICATED_RATING"]))
    _require(answer_count == 0, "human answers existed before protocol freeze")


def _validate_frozen_sources(
    root: Path, human_protocol: Mapping[str, Any]
) -> None:
    integrity = human_protocol["FROZEN_SOURCE_INTEGRITY"]
    _require(
        integrity["BYTE_IDENTITY_BASE_COMMIT"] == STARTING_COMMIT,
        "frozen-source base commit changed",
    )
    hashed_items = [
        integrity["EXTERNAL_AUDIT_PROTOCOL"],
        *integrity["EXTERNAL_AUDIT_PAPER_RECORDS"],
        integrity["ORIGINAL_CROSS_PAPER_ANALYSIS"],
        integrity["CLAIM_LEDGER"],
    ]
    for item in hashed_items:
        relative = Path(item["PATH"])
        path = root / relative
        _require(path.is_file(), f"frozen source missing: {relative}")
        _require(_sha256(path) == item["SHA256"], f"frozen hash changed: {relative}")
        _require(
            path.read_bytes() == _git_object_bytes(root, STARTING_COMMIT, relative),
            f"frozen source differs from starting commit: {relative}",
        )

    sampling_relative = Path(human_protocol["FROZEN_SAMPLE"]["SAMPLING_RULE_PATH"])
    sampling_path = root / sampling_relative
    _require(
        _sha256(sampling_path)
        == human_protocol["FROZEN_SAMPLE"]["SAMPLING_RULE_SHA256"],
        "frozen sampling-rule hash changed",
    )
    _require(
        sampling_path.read_bytes()
        == _git_object_bytes(root, STARTING_COMMIT, sampling_relative),
        "sampling rule differs from the starting commit",
    )

    frozen_scopes = [
        "audits/external-identification-v1",
        integrity["CLAIM_LEDGER"]["PATH"],
        *integrity["POSITIVE_AND_NEGATIVE_CONTROL_SCOPES"],
        *integrity["FINAL_V4_EVIDENCE_SCOPES"],
    ]
    for scope in frozen_scopes:
        _assert_scope_byte_identical(root, STARTING_COMMIT, scope)


def validate_response_record(
    response: Mapping[str, Any],
    ai_adjudicated_status: str,
    location: str,
) -> None:
    """Validate one response without changing the AI-adjudicated status."""

    _require(isinstance(response, Mapping), f"response must be a mapping: {location}")
    _require(
        tuple(response) == HUMAN_RESPONSE_RECORD_FIELDS,
        f"human response fields changed: {location}",
    )
    _require(
        _nonblank(response["REVIEWER_ID_OR_PSEUDONYM"]),
        f"reviewer identifier missing: {location}",
    )
    answer = response["HUMAN_RESPONSE"]
    _require(answer in HUMAN_RESPONSE_OPTIONS, f"invalid human response: {location}")
    preferred = response["HUMAN_PREFERRED_STATUS"]
    rationale = response["HUMAN_RATIONALE"]
    evidence = response["HUMAN_ORIGINAL_SOURCE_EVIDENCE_LOCATION"]
    basis = response["CORRECTION_BASIS"]
    if answer == "DISAGREE":
        _require(preferred in STATUS_ORDER, f"invalid human preferred status: {location}")
        _require(
            preferred != ai_adjudicated_status,
            f"DISAGREE repeats the AI-adjudicated status: {location}",
        )
        _require(_nonblank(rationale), f"human correction lacks rationale: {location}")
        _require(
            _nonblank(evidence),
            f"human correction lacks original-source evidence: {location}",
        )
        _require(
            basis == "EVIDENCE_RATING_CORRECTION",
            f"human correction has an invalid basis: {location}",
        )
    else:
        _require(preferred == "", f"preferred status supplied without DISAGREE: {location}")
        _require(basis == "", f"correction basis supplied without DISAGREE: {location}")
        _require(isinstance(rationale, str), f"human rationale must be text: {location}")
        _require(isinstance(evidence, str), f"human evidence location must be text: {location}")


def derive_human_verification_status(
    responses: Sequence[Mapping[str, Any]],
) -> str | None:
    """Map one or more valid reviewer answers to one cell-level status."""

    if not responses:
        return None
    statuses = {
        HUMAN_STATUS_BY_RESPONSE[response["HUMAN_RESPONSE"]]
        for response in responses
    }
    if "DISPUTED" in statuses:
        return "DISPUTED"
    if "CONFIRMED" in statuses:
        return "CONFIRMED"
    return "UNRESOLVED"


def _normalize_cell_reference(value: Any, location: str) -> tuple[str, str]:
    if isinstance(value, str) and value.count("/") == 1:
        paper_id, criterion_id = value.split("/", 1)
        _require(paper_id and criterion_id, f"invalid cell reference: {location}")
        return paper_id, criterion_id
    if isinstance(value, Mapping):
        _require(
            set(value) == {"PAPER_ID", "CRITERION_ID"},
            f"invalid cell reference fields: {location}",
        )
        return str(value["PAPER_ID"]), str(value["CRITERION_ID"])
    raise HumanVerificationError(f"invalid cell reference: {location}")


def _validate_reviewer_records(
    human_protocol: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    known_paper_ids: set[str],
    expected_priority: set[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    schema = human_protocol["REVIEWER_METADATA_SCHEMA"]
    required_fields = tuple(schema["REQUIRED_FIELDS"])
    integrity_fields = tuple(schema["ADDITIONAL_INTEGRITY_FIELDS"])
    allowed_relationships = set(
        human_protocol["REVIEWER_ELIGIBILITY"]["ALLOWED_RELATIONSHIP_LABELS"]
    )
    records = reconciliation["HUMAN_REVIEWER_RECORDS"]
    _require(isinstance(records, list), "HUMAN_REVIEWER_RECORDS must be a list")
    reviewers: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        location = f"HUMAN_REVIEWER_RECORDS[{index}]"
        _require(isinstance(record, dict), f"reviewer record must be a mapping: {location}")
        _require(
            tuple(record) == required_fields + integrity_fields,
            f"reviewer metadata fields changed: {location}",
        )
        reviewer_id = record["REVIEWER_ID_OR_PSEUDONYM"]
        _require(_nonblank(reviewer_id), f"reviewer identifier missing: {location}")
        _require(reviewer_id not in reviewers, f"duplicate reviewer identifier: {reviewer_id}")
        _require(_nonblank(record["ROLE"]), f"reviewer role missing: {location}")
        _require(
            record["RELATIONSHIP_TO_PROJECT"] in allowed_relationships,
            f"invalid reviewer relationship: {location}",
        )
        _require(_nonblank(record["REVIEW_DATE"]), f"review date missing: {location}")
        _require(
            _nonblank(record["CONFLICTS_OR_PRIOR_INVOLVEMENT"]),
            f"conflicts or prior involvement missing: {location}",
        )
        papers = record["PAPERS_REVIEWED"]
        cells = record["CELLS_REVIEWED"]
        _require(isinstance(papers, list) and papers, f"papers reviewed missing: {location}")
        _require(set(papers) <= known_paper_ids, f"unknown reviewed paper: {location}")
        _require(isinstance(cells, list) and cells, f"cells reviewed missing: {location}")
        normalized_cells = {
            _normalize_cell_reference(value, f"{location}/CELLS_REVIEWED")
            for value in cells
        }
        _require(
            normalized_cells <= expected_priority,
            f"reviewer metadata names a nonpriority cell: {location}",
        )
        _require(
            {paper_id for paper_id, _ in normalized_cells} == set(papers),
            f"papers and cells reviewed disagree: {location}",
        )
        _require(
            record["CONFIRMATION_THAT_REVIEWER_IS_HUMAN"] is True,
            f"reviewer is not confirmed human: {location}",
        )
        for field in integrity_fields:
            _require(
                isinstance(record[field], bool),
                f"reviewer integrity field is not boolean: {location}",
            )
        reviewers[str(reviewer_id)] = {
            **record,
            "NORMALIZED_CELLS_REVIEWED": normalized_cells,
        }
    return reviewers


def _resolve_correction(
    responses: Sequence[Mapping[str, Any]],
    ai_status: str,
    reviewers: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str | None]:
    if len(responses) == 1 and responses[0]["HUMAN_RESPONSE"] == "DISAGREE":
        return str(responses[0]["HUMAN_PREFERRED_STATUS"]), "SINGLE_HUMAN_CORRECTION"
    if len(responses) < 2:
        return ai_status, None

    disagreeing = [
        response for response in responses if response["HUMAN_RESPONSE"] == "DISAGREE"
    ]
    determinate = [
        response
        for response in responses
        if response["HUMAN_RESPONSE"] in {"AGREE", "DISAGREE"}
    ]
    proposed = {response["HUMAN_PREFERRED_STATUS"] for response in disagreeing}
    independent = all(
        not reviewers[response["REVIEWER_ID_OR_PSEUDONYM"]][
            "SUBSTANTIALLY_PARTICIPATED_IN_ORIGINAL_EXTERNAL_AUDIT_RATINGS"
        ]
        and reviewers[response["REVIEWER_ID_OR_PSEUDONYM"]][
            "REVIEWED_WITHOUT_ANOTHER_HUMAN_REVIEWERS_ANSWERS"
        ]
        for response in disagreeing
    )
    no_determinate_conflict = len(determinate) == len(disagreeing)
    if (
        len(disagreeing) >= 2
        and len(proposed) == 1
        and independent
        and no_determinate_conflict
    ):
        return str(next(iter(proposed))), "TWO_HUMAN_CORRECTION"
    return ai_status, None


def _validate_template(
    human_protocol: Mapping[str, Any], template: Mapping[str, Any]
) -> None:
    expected_fields = (
        "TEMPLATE_ID",
        "HUMAN_VERIFICATION_COMPLETED",
        *human_protocol["REVIEWER_METADATA_SCHEMA"]["REQUIRED_FIELDS"],
        *human_protocol["REVIEWER_METADATA_SCHEMA"]["ADDITIONAL_INTEGRITY_FIELDS"],
    )
    _require(tuple(template) == expected_fields, "reviewer template fields changed")
    _require(
        template["HUMAN_VERIFICATION_COMPLETED"] is False,
        "reviewer template falsely marked complete",
    )
    for field in human_protocol["REVIEWER_METADATA_SCHEMA"]["REQUIRED_FIELDS"]:
        expected_blank: Any = [] if field in {"PAPERS_REVIEWED", "CELLS_REVIEWED"} else ""
        _require(template[field] == expected_blank, f"reviewer template prefilled: {field}")
    for field in human_protocol["REVIEWER_METADATA_SCHEMA"]["ADDITIONAL_INTEGRITY_FIELDS"]:
        _require(template[field] == "", f"reviewer template prefilled: {field}")


def validate_human_verification(
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate frozen inputs, selected cells, metadata, and current answers."""

    root = repository_root.resolve()
    human_protocol = _load_yaml(root / PROTOCOL_RELATIVE)
    _validate_protocol_freeze(root, human_protocol)
    _validate_frozen_sources(root, human_protocol)

    _require(
        tuple(human_protocol["FROZEN_RATING_STATES"]) == STATUS_ORDER,
        "frozen rating-state order changed",
    )
    _require(
        tuple(human_protocol["HUMAN_RESPONSE_RULE"]["ALLOWED_RESPONSES"])
        == HUMAN_RESPONSE_OPTIONS,
        "human response options changed",
    )
    _require(
        tuple(
            human_protocol["HUMAN_RESPONSE_RULE"]["PACKET_RESPONSE_STORAGE"][
                "RECORD_FIELDS"
            ]
        )
        == HUMAN_RESPONSE_RECORD_FIELDS,
        "human response record schema changed",
    )
    scope = human_protocol["SCOPE"]
    _require(scope["AUDIT_PAPERS"] == 6, "protocol paper count changed")
    _require(scope["AUDIT_RATING_CELLS"] == 108, "protocol audit cell count changed")
    _require(scope["TOTAL_PRIORITY_CELLS"] == 23, "protocol priority count changed")
    _require(scope["AI_DISAGREEMENT_CELLS"] == 17, "protocol disagreement count changed")
    _require(scope["SAMPLED_AI_AGREEMENT_CELLS"] == 6, "protocol sample count changed")
    _require(
        tuple(
            human_protocol["EXTERNAL_AUDIT_CONCLUSION_RULE"][
                "ALLOWED_HUMAN_VERIFIED_RESULTS"
            ]
        )
        == ALLOWED_HUMAN_VERIFIED_RESULTS,
        "allowed human-verified results changed",
    )
    no_new_science = human_protocol["NO_NEW_SCIENCE"]
    for counter in (
        "EVALUATED_MODEL_RUNS",
        "GPU_USE",
        "UNSEEN_CONFIRMATORY_TARGETS_SCREENED",
        "NEW_REAL_TARGETS_SCREENED",
        "NEW_EXTERNAL_AUDIT_PAPERS",
    ):
        _require(no_new_science[counter] == 0, f"nonzero protocol counter: {counter}")

    integrity = human_protocol["FROZEN_SOURCE_INTEGRITY"]
    audit_protocol = _load_yaml(root / integrity["EXTERNAL_AUDIT_PROTOCOL"]["PATH"])
    requirements = _flatten_requirements(audit_protocol)
    _require(len(requirements) == 18, "frozen criterion count is not 18")
    records: dict[str, dict[str, Any]] = {}
    record_paths: dict[str, Path] = {}
    for item in integrity["EXTERNAL_AUDIT_PAPER_RECORDS"]:
        path = root / item["PATH"]
        record = _load_yaml(path)
        paper_id = record["PAPER_ID"]
        _require(paper_id not in records, f"duplicate frozen paper: {paper_id}")
        records[paper_id] = record
        record_paths[paper_id] = Path(item["PATH"])
    _require(len(records) == 6, "frozen paper count is not six")

    sampling = _load_yaml(root / human_protocol["FROZEN_SAMPLE"]["SAMPLING_RULE_PATH"])
    _require(len(sampling["SELECTED"]) == 6, "sampling file must contain six selections")
    selected_from_file = {
        (item["PAPER_ID"], item["CRITERION"]): item["SHA256"]
        for item in sampling["SELECTED"]
    }
    _require(len(selected_from_file) == 6, "sampled agreement count is not six")
    domain = human_protocol["FROZEN_SAMPLE"]["DOMAIN_SEPARATOR"]
    expected_sample: dict[tuple[str, str], str] = {}
    disagreements: set[tuple[str, str]] = set()
    for paper_id, record in records.items():
        candidates = []
        for criterion_id in requirements:
            a = record["REVIEWER_A_RATINGS"][criterion_id]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion_id]["STATUS"]
            if a == b:
                candidates.append(
                    (_sample_digest(domain, paper_id, criterion_id), criterion_id)
                )
            else:
                disagreements.add((paper_id, criterion_id))
        digest, criterion_id = min(candidates)
        expected_sample[(paper_id, criterion_id)] = digest
    _require(expected_sample == selected_from_file, "agreement sampling rule changed")
    _require(len(disagreements) == 17, "AI disagreement count changed")
    expected_priority = disagreements | set(expected_sample)
    _require(len(expected_priority) == 23, "priority cell count changed")

    frozen_selected = {
        (item["PAPER_ID"], item["CRITERION_ID"]): item["SELECTION_BASIS"]
        for item in human_protocol["FROZEN_SAMPLE"]["SELECTED_CELLS"]
    }
    expected_bases = {
        cell: (
            "REVIEWER_DISAGREEMENT"
            if cell in disagreements
            else "DETERMINISTIC_AGREEMENT_SAMPLE"
        )
        for cell in expected_priority
    }
    _require(frozen_selected == expected_bases, "frozen priority cell identities changed")

    reconciliation = _load_yaml(root / RECONCILIATION_RELATIVE)
    template = _load_yaml(root / REVIEWER_TEMPLATE_RELATIVE)
    _validate_template(human_protocol, template)
    reviewers = _validate_reviewer_records(
        human_protocol,
        reconciliation,
        set(records),
        expected_priority,
    )

    packet_paths = [Path(path) for path in human_protocol["FROZEN_SAMPLE"]["PACKET_PATHS"]]
    _require(len(packet_paths) == 6, "human packet count is not six")
    observed_packet_paths = {
        path.relative_to(root)
        for path in (root / "paper/human-review").glob("[0-9][0-9]-*.yaml")
    }
    _require(
        observed_packet_paths == set(packet_paths),
        "human-review directory does not contain exactly the six frozen packets",
    )
    packet_cell_keys: list[tuple[str, str]] = []
    completed_cells: list[dict[str, Any]] = []
    reviewer_cells: dict[str, set[tuple[str, str]]] = {
        reviewer_id: set() for reviewer_id in reviewers
    }
    packet_completion_flags: list[bool] = []

    for relative in packet_paths:
        packet = _load_yaml(root / relative)
        paper_id = packet["PAPER_ID"]
        _require(paper_id in records, f"unknown packet paper: {paper_id}")
        record = records[paper_id]
        _require(
            packet["FROZEN_PAPER_RECORD"] == record_paths[paper_id].as_posix(),
            f"packet frozen record path changed: {paper_id}",
        )
        _require(
            packet["FROZEN_PAPER_RECORD_SHA256"]
            == _sha256(root / record_paths[paper_id]),
            f"packet frozen record hash changed: {paper_id}",
        )
        _require(
            packet["HUMAN_VERIFICATION_PROTOCOL"] == PROTOCOL_RELATIVE.as_posix(),
            f"packet protocol path changed: {paper_id}",
        )
        _require(
            tuple(packet["HUMAN_RESPONSE_OPTIONS"]) == HUMAN_RESPONSE_OPTIONS,
            f"packet response options changed: {paper_id}",
        )
        _require(
            tuple(packet["HUMAN_RESPONSE_RECORD_FIELDS"])
            == HUMAN_RESPONSE_RECORD_FIELDS,
            f"packet response fields changed: {paper_id}",
        )
        _require(
            [cell["CRITERION_ID"] for cell in packet["CRITERIA"]]
            == list(requirements),
            f"packet criteria changed: {paper_id}",
        )
        packet_priority_complete: list[bool] = []
        for cell in packet["CRITERIA"]:
            criterion_id = cell["CRITERION_ID"]
            key = (paper_id, criterion_id)
            packet_cell_keys.append(key)
            a = record["REVIEWER_A_RATINGS"][criterion_id]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion_id]["STATUS"]
            adjudicated = record["ADJUDICATED_RATINGS"][criterion_id]
            disagreed = a != b
            sampled = key in expected_sample
            priority = key in expected_priority
            _require(
                cell["FROZEN_CRITERION_TEXT"] == requirements[criterion_id],
                f"criterion definition changed in packet: {paper_id}/{criterion_id}",
            )
            _require(cell["REVIEWER_A_RATING"] == a, f"Reviewer A rating overwritten: {key}")
            _require(cell["REVIEWER_B_RATING"] == b, f"Reviewer B rating overwritten: {key}")
            _require(
                cell["ADJUDICATED_RATING"] == adjudicated["STATUS"],
                f"AI-adjudicated rating overwritten: {key}",
            )
            _require(cell["REVIEWERS_DISAGREED"] is disagreed, f"disagreement flag changed: {key}")
            _require(
                cell["PRIORITY_HUMAN_VERIFICATION"] is priority,
                f"nonpriority cell substituted or priority flag changed: {key}",
            )
            expected_reason = (
                "REVIEWER_DISAGREEMENT"
                if disagreed
                else "DETERMINISTIC_AGREEMENT_SAMPLE"
                if sampled
                else "NOT_PRIORITY_SAMPLE"
            )
            _require(cell["PRIORITY_REASON"] == expected_reason, f"priority reason changed: {key}")
            _require(
                cell["EXACT_ORIGINAL_SOURCE_LOCATION"]
                == adjudicated["EVIDENCE_LOCATION"],
                f"packet evidence location changed: {key}",
            )
            _require(
                cell["CONCISE_EVIDENCE_SUMMARY"] == adjudicated["EVIDENCE_SUMMARY"],
                f"packet evidence summary changed: {key}",
            )
            responses = cell["HUMAN_RESPONSES"]
            _require(isinstance(responses, list), f"HUMAN_RESPONSES must be a list: {key}")
            if not priority:
                _require(not responses, f"nonpriority cell contains a human response: {key}")
                continue
            seen_reviewers: set[str] = set()
            for response in responses:
                validate_response_record(
                    response,
                    adjudicated["STATUS"],
                    f"{paper_id}/{criterion_id}",
                )
                reviewer_id = str(response["REVIEWER_ID_OR_PSEUDONYM"])
                _require(reviewer_id not in seen_reviewers, f"duplicate reviewer response: {key}")
                _require(reviewer_id in reviewers, f"response has no reviewer metadata: {key}")
                _require(
                    key in reviewers[reviewer_id]["NORMALIZED_CELLS_REVIEWED"],
                    f"response omitted from reviewer CELLS_REVIEWED: {key}",
                )
                seen_reviewers.add(reviewer_id)
                reviewer_cells[reviewer_id].add(key)
            packet_priority_complete.append(bool(responses))
            if responses:
                human_status = derive_human_verification_status(responses)
                applied_status, correction_label = _resolve_correction(
                    responses,
                    adjudicated["STATUS"],
                    reviewers,
                )
                completed_cells.append(
                    {
                        "PAPER_ID": paper_id,
                        "CRITERION_ID": criterion_id,
                        "PRIORITY_REASON": expected_reason,
                        "REVIEWER_A_STATUS": a,
                        "REVIEWER_B_STATUS": b,
                        "AI_ADJUDICATED_STATUS": adjudicated["STATUS"],
                        "HUMAN_RESPONSES": responses,
                        "HUMAN_VERIFICATION_STATUS": human_status,
                        "HUMAN_VERIFIED_STATUS": applied_status,
                        "CORRECTION_LABEL": correction_label,
                    }
                )
        packet_complete = packet["HUMAN_VERIFICATION_COMPLETED"]
        _require(
            isinstance(packet_complete, bool),
            f"packet completion flag is not boolean: {paper_id}",
        )
        if packet_complete:
            _require(
                all(packet_priority_complete),
                f"packet marked complete while priority cells remain blank: {paper_id}",
            )
        packet_completion_flags.append(packet_complete)

    _require(len(packet_cell_keys) == 108, "human packet cell count is not 108")
    _require(len(set(packet_cell_keys)) == 108, "duplicate or substituted packet cell")
    for reviewer_id, cells in reviewer_cells.items():
        _require(
            cells == reviewers[reviewer_id]["NORMALIZED_CELLS_REVIEWED"],
            f"reviewer CELLS_REVIEWED does not match packet responses: {reviewer_id}",
        )

    reconciliation_priority = reconciliation["PRIORITY_CELLS"]
    _require(
        reconciliation["SAMPLING_RULE"]
        == human_protocol["FROZEN_SAMPLE"]["SAMPLING_RULE_PATH"],
        "reconciliation sampling-rule path changed",
    )
    _require(
        reconciliation["HUMAN_VERIFICATION_PROTOCOL"]
        == PROTOCOL_RELATIVE.as_posix(),
        "reconciliation protocol path changed",
    )
    _require(len(reconciliation_priority) == 23, "reconciliation priority count changed")
    reconciliation_keys: list[tuple[str, str]] = []
    for cell in reconciliation_priority:
        key = (cell["PAPER_ID"], cell["CRITERION_ID"])
        reconciliation_keys.append(key)
        _require(key in expected_priority, f"reconciliation substitutes a nonpriority cell: {key}")
        record = records[key[0]]
        criterion_id = key[1]
        _require(
            cell["FROZEN_CRITERION_TEXT"] == requirements[criterion_id],
            f"reconciliation criterion changed: {key}",
        )
        _require(
            cell["REVIEWER_A_RATING"]
            == record["REVIEWER_A_RATINGS"][criterion_id]["STATUS"],
            f"reconciliation Reviewer A rating changed: {key}",
        )
        _require(
            cell["REVIEWER_B_RATING"]
            == record["REVIEWER_B_RATINGS"][criterion_id]["STATUS"],
            f"reconciliation Reviewer B rating changed: {key}",
        )
        _require(
            cell["ADJUDICATED_RATING"]
            == record["ADJUDICATED_RATINGS"][criterion_id]["STATUS"],
            f"reconciliation AI adjudication changed: {key}",
        )
        _require(
            cell["PRIORITY_REASON"] == expected_bases[key],
            f"reconciliation priority reason changed: {key}",
        )
        _require(
            cell["HUMAN_RESPONSES"] == [],
            f"human response must be recorded in paper packet, not reconciliation: {key}",
        )
    _require(
        set(reconciliation_keys) == expected_priority
        and len(reconciliation_keys) == len(set(reconciliation_keys)),
        "reconciliation priority identities changed",
    )
    _require(
        reconciliation["PRIORITY_DISAGREEMENTS"] == 17,
        "reconciliation disagreement count changed",
    )
    _require(
        reconciliation["DETERMINISTIC_AGREEMENT_SAMPLE"] == 6,
        "reconciliation sample count changed",
    )
    _require(reconciliation["TOTAL_PRIORITY_CELLS"] == 23, "reconciliation priority total changed")

    global_complete = reconciliation["HUMAN_VERIFICATION_COMPLETED"]
    _require(isinstance(global_complete, bool), "global completion flag is not boolean")
    if global_complete:
        _require(
            len(completed_cells) == 23,
            "HUMAN_VERIFICATION_COMPLETED while priority cells remain blank",
        )
        _require(
            all(packet_completion_flags),
            "global completion marked before all packet completion flags",
        )
        _require(reviewers, "global completion marked without reviewer metadata")

    correction_count = sum(
        cell["CORRECTION_LABEL"] is not None for cell in completed_cells
    )
    if global_complete and correction_count:
        _require(
            reconciliation["HUMAN_VERIFIED_RESULT"]
            in ALLOWED_HUMAN_VERIFIED_RESULTS,
            "completed corrected review lacks an allowed HUMAN_VERIFIED_RESULT",
        )
        _require(
            _nonblank(reconciliation["HUMAN_VERIFIED_RESULT_RATIONALE"]),
            "completed corrected review lacks a qualitative-result rationale",
        )
    elif global_complete:
        _require(
            reconciliation["HUMAN_VERIFIED_RESULT"]
            in {"", "FRAMEWORK_PARTIALLY_DISTINCTIVE"},
            "uncorrected human layer cannot change the novelty result",
        )

    status_counts = Counter(
        cell["HUMAN_VERIFICATION_STATUS"] for cell in completed_cells
    )
    disagreement_cells = [
        cell
        for cell in completed_cells
        if cell["PRIORITY_REASON"] == "REVIEWER_DISAGREEMENT"
    ]
    sampled_cells = [
        cell
        for cell in completed_cells
        if cell["PRIORITY_REASON"] == "DETERMINISTIC_AGREEMENT_SAMPLE"
    ]
    determinate = status_counts["CONFIRMED"] + status_counts["DISPUTED"]
    agreement_rate = (
        status_counts["CONFIRMED"] / determinate if determinate else None
    )
    summary = {
        "VALID": True,
        "PROTOCOL_FREEZE_COMMIT": PROTOCOL_FREEZE_COMMIT,
        "PROTOCOL_COMMITTED_BEFORE_HUMAN_RESPONSES": True,
        "PACKETS": 6,
        "TOTAL_PRIORITY_CELLS": 23,
        "HUMAN_CELLS_COMPLETED": len(completed_cells),
        "CONFIRMED": status_counts["CONFIRMED"],
        "DISPUTED": status_counts["DISPUTED"],
        "UNRESOLVED": status_counts["UNRESOLVED"],
        "AGREEMENT_RATE_AMONG_DETERMINATE_HUMAN_JUDGMENTS": agreement_rate,
        "AI_DISAGREEMENT_CELLS": 17,
        "AI_DISAGREEMENT_CELLS_HUMAN_CONFIRMED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "CONFIRMED"
            for cell in disagreement_cells
        ),
        "AI_DISAGREEMENT_CELLS_HUMAN_DISPUTED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "DISPUTED"
            for cell in disagreement_cells
        ),
        "AI_DISAGREEMENT_CELLS_HUMAN_UNRESOLVED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "UNRESOLVED"
            for cell in disagreement_cells
        ),
        "SAMPLED_AI_AGREEMENT_CELLS": 6,
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_CONFIRMED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "CONFIRMED"
            for cell in sampled_cells
        ),
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_DISPUTED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "DISPUTED"
            for cell in sampled_cells
        ),
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_UNRESOLVED": sum(
            cell["HUMAN_VERIFICATION_STATUS"] == "UNRESOLVED"
            for cell in sampled_cells
        ),
        "SAMPLE_RULE_VERIFIED": True,
        "HUMAN_RESPONSES_CURRENTLY_BLANK": len(completed_cells) == 0,
        "HUMAN_VERIFICATION_COMPLETED": global_complete,
        "ORIGINAL_AI_AUDIT_PRESERVED": True,
        "ORIGINAL_CLAIM_LEDGER_PRESERVED": True,
        "ORIGINAL_POSITIVE_CONTROL_PRESERVED": True,
        "ORIGINAL_V4_EVIDENCE_PRESERVED": True,
        "POST_REVIEW_OVERLAY_READY": True,
        "HUMAN_RESPONSE_OPTIONS": list(HUMAN_RESPONSE_OPTIONS),
        "CORRECTIONS_READY_FOR_OVERLAY": correction_count,
        "EVALUATED_MODEL_RUNS": no_new_science["EVALUATED_MODEL_RUNS"],
        "GPU_USE": no_new_science["GPU_USE"],
        "UNSEEN_CONFIRMATORY_TARGETS_SCREENED": no_new_science[
            "UNSEEN_CONFIRMATORY_TARGETS_SCREENED"
        ],
        "NEW_REAL_TARGETS_SCREENED": no_new_science["NEW_REAL_TARGETS_SCREENED"],
        "NEW_EXTERNAL_AUDIT_PAPERS": no_new_science["NEW_EXTERNAL_AUDIT_PAPERS"],
        "CELLS": completed_cells,
        "RECORDS": records,
        "REQUIREMENTS": requirements,
        "RECONCILIATION": reconciliation,
    }
    return summary


def build_human_verified_overlay(
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Build, but do not persist, the completed HUMAN_VERIFIED_ANALYSIS layer."""

    state = validate_human_verification(repository_root)
    _require(
        state["HUMAN_VERIFICATION_COMPLETED"] is True,
        "cannot build HUMAN_VERIFIED_ANALYSIS before all 23 cells are complete",
    )
    records = state["RECORDS"]
    requirements = state["REQUIREMENTS"]
    reconciliation = state["RECONCILIATION"]
    independent_wording_allowed = all(
        not record[
            "SUBSTANTIALLY_PARTICIPATED_IN_ORIGINAL_EXTERNAL_AUDIT_RATINGS"
        ]
        for record in reconciliation["HUMAN_REVIEWER_RECORDS"]
    )
    corrections = {
        (cell["PAPER_ID"], cell["CRITERION_ID"]): cell
        for cell in state["CELLS"]
        if cell["CORRECTION_LABEL"] is not None
    }
    matrix: dict[str, dict[str, str]] = {}
    for paper_id, record in records.items():
        matrix[paper_id] = {}
        for criterion_id in requirements:
            key = (paper_id, criterion_id)
            original = record["ADJUDICATED_RATINGS"][criterion_id]["STATUS"]
            matrix[paper_id][criterion_id] = (
                corrections[key]["HUMAN_VERIFIED_STATUS"]
                if key in corrections
                else original
            )

    ai_result = "FRAMEWORK_PARTIALLY_DISTINCTIVE"
    if corrections:
        human_result = reconciliation["HUMAN_VERIFIED_RESULT"]
        result_rationale = reconciliation["HUMAN_VERIFIED_RESULT_RATIONALE"]
    else:
        human_result = ai_result
        result_rationale = (
            "No human-reviewed correction was applied; the frozen AI-adjudicated "
            "matrix and qualitative result remain unchanged."
        )
    result_changed = human_result != ai_result
    if corrections and not result_changed:
        comparison_statement = (
            "The qualitative external-audit conclusion was robust to the "
            "human-reviewed corrections."
        )
    elif corrections:
        comparison_statement = (
            "The human-reviewed corrections changed the qualitative external-audit "
            "conclusion; both results are preserved below."
        )
    else:
        comparison_statement = (
            "No human-reviewed correction was applied; the original conclusion "
            "is preserved."
        )

    counts_by_criterion = {
        criterion_id: _status_counts(
            matrix[paper_id][criterion_id] for paper_id in records
        )
        for criterion_id in requirements
    }
    counts_by_paper = {
        paper_id: {
            **_status_counts(statuses.values()),
            "APPLICABLE_CRITERIA": 18
            - sum(status == "NOT_APPLICABLE" for status in statuses.values()),
        }
        for paper_id, statuses in matrix.items()
    }
    total_counts = _status_counts(
        status for statuses in matrix.values() for status in statuses.values()
    )
    reviewed_cells = []
    for cell in state["CELLS"]:
        reviewed_cells.append(
            {
                "PAPER_ID": cell["PAPER_ID"],
                "CRITERION_ID": cell["CRITERION_ID"],
                "PRIORITY_REASON": cell["PRIORITY_REASON"],
                "REVIEWER_A_STATUS": cell["REVIEWER_A_STATUS"],
                "REVIEWER_B_STATUS": cell["REVIEWER_B_STATUS"],
                "AI_ADJUDICATED_STATUS": cell["AI_ADJUDICATED_STATUS"],
                "HUMAN_RESPONSES": cell["HUMAN_RESPONSES"],
                "HUMAN_VERIFICATION_STATUS": cell["HUMAN_VERIFICATION_STATUS"],
                "HUMAN_VERIFIED_STATUS": cell["HUMAN_VERIFIED_STATUS"],
                "CORRECTION_LABEL": cell["CORRECTION_LABEL"],
            }
        )
    scope_description = (
        "Independent human verification of all AI-review disagreements plus a "
        "mechanically sampled set of agreements; not a full 108-cell human review."
        if independent_wording_allowed
        else "Human verification of all AI-review disagreements plus a mechanically "
        "sampled set of agreements, with reviewer relationships disclosed; not a "
        "full 108-cell human review."
    )
    return {
        "ANALYSIS_LAYER": "HUMAN_VERIFIED_ANALYSIS",
        "SOURCE_LAYER": "AI_ADJUDICATED",
        "PROTOCOL": PROTOCOL_RELATIVE.as_posix(),
        "PROTOCOL_FREEZE_COMMIT": PROTOCOL_FREEZE_COMMIT,
        "HUMAN_VERIFICATION_COMPLETED": True,
        "SCOPE_DESCRIPTION": scope_description,
        "INDEPENDENT_WORDING_ALLOWED": independent_wording_allowed,
        "TOTAL_PRIORITY_CELLS": state["TOTAL_PRIORITY_CELLS"],
        "HUMAN_CELLS_COMPLETED": state["HUMAN_CELLS_COMPLETED"],
        "CONFIRMED": state["CONFIRMED"],
        "DISPUTED": state["DISPUTED"],
        "UNRESOLVED": state["UNRESOLVED"],
        "AGREEMENT_RATE_AMONG_DETERMINATE_HUMAN_JUDGMENTS": state[
            "AGREEMENT_RATE_AMONG_DETERMINATE_HUMAN_JUDGMENTS"
        ],
        "AI_DISAGREEMENT_CELLS": state["AI_DISAGREEMENT_CELLS"],
        "AI_DISAGREEMENT_CELLS_HUMAN_CONFIRMED": state[
            "AI_DISAGREEMENT_CELLS_HUMAN_CONFIRMED"
        ],
        "AI_DISAGREEMENT_CELLS_HUMAN_DISPUTED": state[
            "AI_DISAGREEMENT_CELLS_HUMAN_DISPUTED"
        ],
        "AI_DISAGREEMENT_CELLS_HUMAN_UNRESOLVED": state[
            "AI_DISAGREEMENT_CELLS_HUMAN_UNRESOLVED"
        ],
        "SAMPLED_AI_AGREEMENT_CELLS": state["SAMPLED_AI_AGREEMENT_CELLS"],
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_CONFIRMED": state[
            "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_CONFIRMED"
        ],
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_DISPUTED": state[
            "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_DISPUTED"
        ],
        "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_UNRESOLVED": state[
            "SAMPLED_AI_AGREEMENT_CELLS_HUMAN_UNRESOLVED"
        ],
        "ORIGINAL_AI_AUDIT_PRESERVED": True,
        "CORRECTED_CELL_COUNT": len(corrections),
        "REVIEWED_CELLS": reviewed_cells,
        "MATRIX_RECOMPUTED": bool(corrections),
        "HUMAN_VERIFIED_MATRIX": matrix if corrections else None,
        "COUNTS_BY_CRITERION": counts_by_criterion if corrections else None,
        "COUNTS_BY_PAPER": counts_by_paper if corrections else None,
        "TOTAL_STATUS_COUNTS": total_counts if corrections else None,
        "AI_ADJUDICATED_RESULT": ai_result,
        "HUMAN_VERIFIED_RESULT": human_result,
        "HUMAN_VERIFIED_RESULT_RATIONALE": result_rationale,
        "AGGREGATE_CONCLUSION_CHANGED": result_changed,
        "CONCLUSION_COMPARISON_STATEMENT": comparison_statement,
    }


def write_human_verified_overlay(
    output: Path,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    """Persist the completed overlay only at its designated new YAML path."""

    root = repository_root.resolve()
    expected_output = (root / OVERLAY_RELATIVE).resolve()
    resolved_output = output.resolve()
    _require(
        resolved_output == expected_output,
        f"overlay output must be {OVERLAY_RELATIVE.as_posix()}",
    )
    _require(not resolved_output.exists(), "refusing to overwrite an existing overlay")
    overlay = build_human_verified_overlay(root)
    resolved_output.write_text(_yaml_text(overlay), encoding="utf-8")


def _public_validation_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    hidden = {"CELLS", "RECORDS", "REQUIREMENTS", "RECONCILIATION"}
    return {key: value for key, value in state.items() if key not in hidden}


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository worktree to validate",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate current state without writing an overlay",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"write a completed overlay to {OVERLAY_RELATIVE.as_posix()}",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    if args.validate_only and args.output is not None:
        print("HUMAN_VERIFICATION_VALIDATOR: FAIL")
        print("ERROR: choose --validate-only or --output, not both")
        return 2
    try:
        state = validate_human_verification(args.repository_root)
        if args.output is not None:
            write_human_verified_overlay(args.output, args.repository_root)
            print(f"HUMAN_VERIFIED_ANALYSIS_WRITTEN: {OVERLAY_RELATIVE.as_posix()}")
        else:
            print("HUMAN_VERIFICATION_VALIDATOR: PASS")
            print(_yaml_text(_public_validation_summary(state)).rstrip())
    except Exception as error:
        print("HUMAN_VERIFICATION_VALIDATOR: FAIL")
        print(f"ERROR: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
