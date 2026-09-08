#!/usr/bin/env python3
"""Mechanically validate the frozen external-identification audit."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import subprocess
from typing import Any, Iterable

from ruamel.yaml import YAML


BASE_COMMIT = "783a4cb151631092cea8a0633f4f050db7c4a381"
PROTOCOL_COMMIT = "1ae78e0ff13f1c82c8ce26f8024d3cd859654ea5"
PROMPT_COMMIT = "f6c0831bae15f9579c20ab16323b06c6d9e0c100"
RAW_REVIEW_COMMIT = "3136a54c5cefd1f217996c645488d83325612d7e"

PROTOCOL_RELATIVE = Path("protocols/external-identification-audit-v1.yaml")
PROMPT_RELATIVE = Path(
    "audits/external-identification-v1/reviewer-prompt-v1.yaml"
)
AUDIT_RELATIVE = Path("audits/external-identification-v1")
PAPER_RELATIVE = AUDIT_RELATIVE / "papers"
RAW_RELATIVES = (
    AUDIT_RELATIVE / "raw/reviewer-a.yaml",
    AUDIT_RELATIVE / "raw/reviewer-b.yaml",
)
PAPER_FILENAMES = (
    "01-basm-when-not-to-imitate.yaml",
    "02-agent-skills-can-be-harmful.yaml",
    "03-slbench.yaml",
    "04-swe-skills-bench.yaml",
    "05-experience-driven-self-evolving-safety.yaml",
    "06-securevibebench.yaml",
)
STATUS_ORDER = (
    "ESTABLISHED",
    "NOT_ESTABLISHED",
    "UNDETERMINED",
    "NOT_APPLICABLE",
)
RAW_HASHES = {
    RAW_RELATIVES[0]: "743f26d675c0578adf534229cdf380b708a9f6450dc679411c0a030649d06820",
    RAW_RELATIVES[1]: "94ac0e3f027af0bab8c659971248266fdf3e62f6aae35a2b9078c6982566cdaf",
}


class ExternalAuditValidationError(AssertionError):
    """Raised when an audit integrity condition does not hold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExternalAuditValidationError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    data = parser.load(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), f"{path} must contain a YAML mapping")
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(
    root: Path, *arguments: str, check: bool = True, text: bool = True
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=text,
    )


def _git_lines(root: Path, *arguments: str) -> list[str]:
    result = _git(root, *arguments)
    assert isinstance(result.stdout, str)
    return result.stdout.splitlines()


def _git_object_bytes(root: Path, revision: str, relative: Path) -> bytes:
    result = _git(
        root,
        "show",
        f"{revision}:{relative.as_posix()}",
        text=False,
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


def _criteria(protocol: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (criterion, definition)
        for group in protocol["IDENTIFICATION_REQUIREMENTS"].values()
        for criterion, definition in group.items()
    ]


def _paper_ids(protocol: dict[str, Any]) -> list[str]:
    return [paper["PAPER_ID"] for paper in protocol["PRIMARY_AUDIT_TARGETS"]]


def _index_papers(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {paper["PAPER_ID"]: paper for paper in review["PAPERS"]}


def _status_counts(statuses: Iterable[str]) -> dict[str, int]:
    counts = Counter(statuses)
    return {status: counts[status] for status in STATUS_ORDER}


def _validate_commit_freezes(root: Path) -> None:
    _require(
        _git_lines(root, "rev-parse", f"{PROTOCOL_COMMIT}^")[0] == BASE_COMMIT,
        "protocol commit must be based directly on the requested starting commit",
    )
    _require(
        _git_lines(root, "rev-parse", f"{PROMPT_COMMIT}^")[0] == PROTOCOL_COMMIT,
        "reviewer-prompt commit must directly follow the protocol freeze",
    )
    _require(
        _git_lines(root, "rev-parse", f"{RAW_REVIEW_COMMIT}^")[0]
        == PROMPT_COMMIT,
        "raw-review freeze must directly follow the reviewer prompt",
    )
    expected_commit_paths = {
        PROTOCOL_COMMIT: [PROTOCOL_RELATIVE.as_posix()],
        PROMPT_COMMIT: [PROMPT_RELATIVE.as_posix()],
        RAW_REVIEW_COMMIT: sorted(path.as_posix() for path in RAW_RELATIVES),
    }
    for commit, expected in expected_commit_paths.items():
        observed = sorted(
            _git_lines(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
        )
        _require(observed == sorted(expected), f"unexpected paths in freeze commit {commit}")

    protocol_bytes = (root / PROTOCOL_RELATIVE).read_bytes()
    _require(
        protocol_bytes == _git_object_bytes(root, PROTOCOL_COMMIT, PROTOCOL_RELATIVE),
        "frozen protocol differs from its commit",
    )
    prompt_bytes = (root / PROMPT_RELATIVE).read_bytes()
    _require(
        prompt_bytes == _git_object_bytes(root, PROMPT_COMMIT, PROMPT_RELATIVE),
        "frozen reviewer prompt differs from its commit",
    )
    for relative, expected_hash in RAW_HASHES.items():
        current = root / relative
        _require(_sha256(current) == expected_hash, f"raw review changed: {relative}")
        _require(
            current.read_bytes()
            == _git_object_bytes(root, RAW_REVIEW_COMMIT, relative),
            f"raw review differs from freeze commit: {relative}",
        )


def _validate_protocol(protocol: dict[str, Any]) -> None:
    _require(protocol["BASE_COMMIT"] == BASE_COMMIT, "wrong protocol base commit")
    for flag in (
        "NOT_A_PREVALENCE_STUDY",
        "NOT_A_BENCHMARK_RANKING",
        "NOT_A_CLAIM_THAT_OTHER_PAPERS_ARE_INVALID",
        "NOT_BLINDED_TO_LITERATURE_SELECTION",
    ):
        _require(protocol[flag] is True, f"protocol flag not true: {flag}")
    _require(len(protocol["PRIMARY_AUDIT_TARGETS"]) == 6, "target count is not six")
    _require(len(_criteria(protocol)) == 18, "criterion count is not 18")
    _require(protocol["CRITERIA_COUNT"] == 18, "declared criterion count is wrong")
    _require(tuple(protocol["ALLOWED_STATUSES"]) == STATUS_ORDER, "status vocabulary changed")
    _require(protocol["REVIEW_MODE"] == "TWO_ISOLATED_AI_REVIEWERS", "wrong review mode")


def _validate_rating(
    rating: dict[str, Any],
    expected_fields: list[str],
    location: str,
) -> None:
    _require(list(rating) == expected_fields, f"rating fields changed at {location}")
    status = rating["STATUS"]
    _require(status in STATUS_ORDER, f"invalid status at {location}: {status}")
    if status == "NOT_APPLICABLE":
        _require(
            bool(str(rating["APPLICABILITY_RATIONALE"]).strip()),
            f"missing applicability rationale at {location}",
        )
    else:
        _require(
            bool(str(rating["EVIDENCE_LOCATION"]).strip()),
            f"missing evidence location at {location}",
        )
        _require(
            bool(str(rating["EVIDENCE_SUMMARY"]).strip()),
            f"missing evidence summary at {location}",
        )


def _validate_raw_reviews(
    protocol: dict[str, Any], prompt: dict[str, Any], reviews: list[dict[str, Any]]
) -> None:
    expected_ids = _paper_ids(protocol)
    expected_criteria = [criterion for criterion, _ in _criteria(protocol)]
    top_fields = prompt["OUTPUT_RULES"]["TOP_LEVEL_FIELDS"]
    paper_fields = prompt["OUTPUT_RULES"]["PAPER_FIELDS"]
    rating_fields = prompt["OUTPUT_RULES"]["RATING_FIELDS"]
    for review in reviews:
        reviewer = review["REVIEWER"]
        _require(list(review) == top_fields, f"top-level raw schema changed: {reviewer}")
        _require(
            [paper["PAPER_ID"] for paper in review["PAPERS"]] == expected_ids,
            f"paper order changed: {reviewer}",
        )
        for counter in (
            "EVALUATED_MODEL_RUNS",
            "GPU_USE",
            "UNSEEN_CONFIRMATORY_TARGETS_SCREENED",
        ):
            _require(review[counter] == 0, f"nonzero {counter}: {reviewer}")
        for paper in review["PAPERS"]:
            paper_id = paper["PAPER_ID"]
            _require(
                list(paper) == paper_fields,
                f"paper schema changed: {reviewer}/{paper_id}",
            )
            _require(
                list(paper["RATINGS"]) == expected_criteria,
                f"criterion order changed: {reviewer}/{paper_id}",
            )
            for criterion, rating in paper["RATINGS"].items():
                _validate_rating(
                    rating,
                    rating_fields,
                    f"{reviewer}/{paper_id}/{criterion}",
                )


def _raw_agreement(
    protocol: dict[str, Any], reviews: list[dict[str, Any]]
) -> tuple[
    int,
    dict[str, int],
    Counter[tuple[str, str]],
    set[tuple[str, str]],
]:
    papers_a = _index_papers(reviews[0])
    papers_b = _index_papers(reviews[1])
    agreement = 0
    by_criterion: Counter[str] = Counter()
    disagreement_types: Counter[tuple[str, str]] = Counter()
    disagreements: set[tuple[str, str]] = set()
    for paper_id in _paper_ids(protocol):
        for criterion, _ in _criteria(protocol):
            status_a = papers_a[paper_id]["RATINGS"][criterion]["STATUS"]
            status_b = papers_b[paper_id]["RATINGS"][criterion]["STATUS"]
            if status_a == status_b:
                agreement += 1
                by_criterion[criterion] += 1
            else:
                disagreements.add((paper_id, criterion))
                disagreement_types[tuple(sorted((status_a, status_b)))] += 1
    return agreement, dict(by_criterion), disagreement_types, disagreements


def _validate_reconciliation(
    protocol: dict[str, Any],
    reviews: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    agreement, by_criterion, types, disagreements = _raw_agreement(protocol, reviews)
    reported = reconciliation["AGREEMENT"]
    _require(reported["TOTAL_CELLS"] == 108, "wrong agreement denominator")
    _require(reported["EXACT_AGREEMENT_COUNT"] == agreement, "wrong agreement count")
    _require(
        reported["DISAGREEMENT_COUNT"] == 108 - agreement,
        "wrong disagreement count",
    )
    _require(
        reported["EXACT_AGREEMENT_PERCENT"] == round(agreement / 108 * 100, 2),
        "wrong agreement percentage",
    )
    reported_types = {
        tuple(sorted(item["STATUSES"])): item["COUNT"]
        for item in reported["DISAGREEMENT_TYPES_UNORDERED"]
    }
    _require(reported_types == dict(types), "wrong disagreement-type counts")
    for criterion, values in reported["BY_CRITERION"].items():
        count = by_criterion.get(criterion, 0)
        _require(values["AGREEMENT_COUNT"] == count, f"wrong agreement for {criterion}")
        _require(values["TOTAL"] == 6, f"wrong criterion denominator: {criterion}")
        _require(
            values["AGREEMENT_PERCENT"] == round(count / 6 * 100, 2),
            f"wrong criterion percentage: {criterion}",
        )

    adjudications = {
        (item["PAPER_ID"], item["CRITERION"]): item
        for item in reconciliation["ADJUDICATIONS"]
    }
    _require(set(adjudications) == disagreements, "adjudications do not match disagreements")
    papers_a = _index_papers(reviews[0])
    papers_b = _index_papers(reviews[1])
    for (paper_id, criterion), item in adjudications.items():
        _require(
            item["ORIGINAL_A"]
            == papers_a[paper_id]["RATINGS"][criterion]["STATUS"],
            f"wrong ORIGINAL_A at {paper_id}/{criterion}",
        )
        _require(
            item["ORIGINAL_B"]
            == papers_b[paper_id]["RATINGS"][criterion]["STATUS"],
            f"wrong ORIGINAL_B at {paper_id}/{criterion}",
        )
        _require(
            item["FINAL_ADJUDICATED"] in STATUS_ORDER,
            f"invalid final adjudication at {paper_id}/{criterion}",
        )
        _require(bool(str(item["EVIDENCE"]).strip()), f"missing adjudication evidence")
        _require(bool(str(item["RATIONALE"]).strip()), f"missing adjudication rationale")
    _require(reconciliation["ADJUDICATION_COMPLETE"] is True, "adjudication incomplete")
    _require(reconciliation["UNRESOLVED_DISAGREEMENTS"] == 0, "unresolved disagreements")
    return adjudications


def _validate_paper_records(
    root: Path,
    protocol: dict[str, Any],
    reviews: list[dict[str, Any]],
    adjudications: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    paths = [root / PAPER_RELATIVE / filename for filename in PAPER_FILENAMES]
    _require(all(path.is_file() for path in paths), "one or more paper records are missing")
    papers = [_load_yaml(path) for path in paths]
    expected_ids = _paper_ids(protocol)
    _require([paper["PAPER_ID"] for paper in papers] == expected_ids, "paper record order changed")
    expected_fields = protocol["PAPER_RECORD_REQUIRED_FIELDS"]
    rating_fields = protocol["PER_CRITERION_REQUIRED_FIELDS"]
    criteria = [criterion for criterion, _ in _criteria(protocol)]
    papers_a = _index_papers(reviews[0])
    papers_b = _index_papers(reviews[1])

    for paper in papers:
        paper_id = paper["PAPER_ID"]
        _require(list(paper) == expected_fields, f"wrong final paper schema: {paper_id}")
        _require(bool(paper["TITLE"]), f"missing title: {paper_id}")
        _require(bool(paper["AUTHORS"]), f"missing authors: {paper_id}")
        _require(bool(paper["SOURCE_URLS"]), f"missing source URLs: {paper_id}")
        _require(
            paper["REVIEWER_A_RATINGS"] == papers_a[paper_id]["RATINGS"],
            f"reviewer A ratings changed in paper record: {paper_id}",
        )
        _require(
            paper["REVIEWER_B_RATINGS"] == papers_b[paper_id]["RATINGS"],
            f"reviewer B ratings changed in paper record: {paper_id}",
        )
        for block in (
            "REVIEWER_A_RATINGS",
            "REVIEWER_B_RATINGS",
            "ADJUDICATED_RATINGS",
        ):
            _require(list(paper[block]) == criteria, f"wrong criteria: {paper_id}/{block}")
            for criterion, rating in paper[block].items():
                _validate_rating(rating, rating_fields, f"{paper_id}/{block}/{criterion}")

        for criterion in criteria:
            status_a = papers_a[paper_id]["RATINGS"][criterion]["STATUS"]
            status_b = papers_b[paper_id]["RATINGS"][criterion]["STATUS"]
            final = paper["ADJUDICATED_RATINGS"][criterion]["STATUS"]
            if status_a == status_b:
                _require(final == status_a, f"agreed status changed: {paper_id}/{criterion}")
            else:
                _require(
                    final == adjudications[(paper_id, criterion)]["FINAL_ADJUDICATED"],
                    f"adjudicated status mismatch: {paper_id}/{criterion}",
                )
    return papers


def _validate_cross_paper(
    root: Path, protocol: dict[str, Any], papers: list[dict[str, Any]]
) -> None:
    analysis = _load_yaml(root / AUDIT_RELATIVE / "cross-paper-analysis.yaml")
    criteria = [criterion for criterion, _ in _criteria(protocol)]
    _require(list(analysis["COUNTS_BY_CRITERION"]) == criteria, "aggregate criterion order changed")
    for criterion in criteria:
        observed = _status_counts(
            paper["ADJUDICATED_RATINGS"][criterion]["STATUS"] for paper in papers
        )
        _require(
            analysis["COUNTS_BY_CRITERION"][criterion] == observed,
            f"aggregate criterion count mismatch: {criterion}",
        )
    observed_total = _status_counts(
        rating["STATUS"]
        for paper in papers
        for rating in paper["ADJUDICATED_RATINGS"].values()
    )
    _require(analysis["TOTAL_STATUS_COUNTS"] == observed_total, "total counts mismatch")
    for paper in papers:
        paper_id = paper["PAPER_ID"]
        observed = _status_counts(
            rating["STATUS"] for rating in paper["ADJUDICATED_RATINGS"].values()
        )
        reported = analysis["COUNTS_BY_PAPER"][paper_id]
        for status in STATUS_ORDER:
            _require(reported[status] == observed[status], f"paper count mismatch: {paper_id}")
        _require(
            reported["APPLICABLE_CRITERIA"] == 18 - observed["NOT_APPLICABLE"],
            f"applicable count mismatch: {paper_id}",
        )
    _require(
        analysis["STRONGER_ESTIMAND_REUSE"]["PAPERS_ESTABLISHING_ALL_18_REQUIREMENTS"]
        == 0,
        "unexpected full-contract count",
    )
    _require(
        analysis["NOVELTY_STRESS_TEST"]["RESULT"]
        == "FRAMEWORK_PARTIALLY_DISTINCTIVE",
        "novelty decision changed",
    )


def _validate_table_data(
    root: Path, protocol: dict[str, Any], papers: list[dict[str, Any]]
) -> None:
    table = _load_yaml(root / AUDIT_RELATIVE / "table-data.yaml")
    criteria = _criteria(protocol)
    paper_ids = _paper_ids(protocol)
    primary = table["REQUIREMENTS_BY_PAPER"]
    _require(primary["ROW_COUNT"] == 18, "table row count is not 18")
    _require(primary["COLUMN_COUNT"] == 6, "table column count is not six")
    _require(tuple(primary["CELL_STATUS_VOCABULARY"]) == STATUS_ORDER, "table vocabulary changed")
    _require(len(primary["ROWS"]) == 18, "table rows missing")
    for row, (criterion, definition) in zip(primary["ROWS"], criteria, strict=True):
        _require(row["CRITERION"] == criterion, f"wrong table criterion: {criterion}")
        _require(row["DEFINITION"] == definition, f"criterion definition changed: {criterion}")
        expected = {
            paper["PAPER_ID"]: paper["ADJUDICATED_RATINGS"][criterion]["STATUS"]
            for paper in papers
        }
        _require(row["CELLS"] == expected, f"table cells mismatch: {criterion}")
    compact = table["CLAIM_DESIGN_GAP_BY_PAPER"]
    _require(compact["ROW_COUNT"] == 6, "compact table row count is not six")
    _require(
        [row["PAPER_ID"] for row in compact["ROWS"]] == paper_ids,
        "compact table paper order changed",
    )
    for row, paper in zip(compact["ROWS"], papers, strict=True):
        _require(row["STATED_CLAIM"] == paper["STATED_PRIMARY_CLAIM"], "claim table mismatch")
        _require(row["DESIGN_ESTABLISHES"] == paper["SUPPORTED_INTERPRETATION"], "design table mismatch")
        _require(
            row["ADDITIONAL_EVIDENCE_FOR_STRONGER_SECURITY_TRANSFER_CLAIM"]
            == paper["ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND"],
            "gap table mismatch",
        )


def _validate_generic_comparison(
    root: Path, protocol: dict[str, Any]
) -> None:
    comparison = _load_yaml(
        root / AUDIT_RELATIVE / "generic-validity-comparison.yaml"
    )
    criteria = [criterion for criterion, _ in _criteria(protocol)]
    _require(
        comparison["PRIMARY_EMPIRICAL_TARGET_COUNT_UNCHANGED"] == 6,
        "generic comparison added a scored target",
    )
    ratings = comparison["REQUIREMENT_CLASSIFICATIONS"]
    _require(list(ratings) == criteria, "generic comparison criterion order changed")
    allowed = {
        "GENERIC_VALIDITY_PRINCIPLE",
        "SECURITY_PROCEDURAL_TRANSFER_SPECIALIZATION",
    }
    counts = Counter()
    for criterion, value in ratings.items():
        classification = value["CLASSIFICATION"]
        _require(classification in allowed, f"bad generic label: {criterion}")
        counts[classification] += 1
    _require(
        comparison["CLASSIFICATION_COUNTS"] == dict(counts),
        "generic classification counts mismatch",
    )


def _validate_provenance(root: Path) -> None:
    provenance = _load_yaml(root / AUDIT_RELATIVE / "provenance.yaml")
    _require(provenance["BASE_COMMIT"] == BASE_COMMIT, "provenance base changed")
    assertions = provenance["INTEGRITY_ASSERTIONS"]
    for counter in (
        "PRIMARY_TARGET_SUBSTITUTIONS",
        "ADDITIONAL_SCORED_PAPERS",
        "EVALUATED_MODEL_RUNS",
        "GPU_USE",
        "UNSEEN_CONFIRMATORY_TARGETS_SCREENED",
    ):
        _require(assertions[counter] == 0, f"nonzero provenance counter: {counter}")
    for flag in (
        "REAL_PAIR_SEARCH_PERFORMED",
        "V5_AUTHORIZED",
        "REAL_V4_RESULT_MODIFIED",
        "POSITIVE_CONTROL_RESULT_MODIFIED",
        "FROZEN_V4_SCIENTIFIC_PREDICATES_MODIFIED",
        "RAW_REVIEW_OUTPUTS_MODIFIED_AFTER_FREEZE",
    ):
        _require(assertions[flag] is False, f"integrity flag not false: {flag}")
    _require(
        provenance["INDEPENDENCE_PROCEDURE"]["RAW_OUTPUTS_COMMITTED_BEFORE_RECONCILIATION"]
        is True,
        "raw-review timing assertion is false",
    )
    _require(
        provenance["INDEPENDENCE_PROCEDURE"]["HUMAN_REVIEWERS_USED"] is False,
        "AI reviewers mislabeled as human",
    )


def _allowed_change(path: str) -> bool:
    allowed_exact = {
        PROTOCOL_RELATIVE.as_posix(),
        "scripts/build_external_identification_audit.py",
        "scripts/validate_external_identification_audit.py",
        "tests/test_external_identification_audit.py",
    }
    return path in allowed_exact or path.startswith(f"{AUDIT_RELATIVE.as_posix()}/")


def _validate_worktree_scope(root: Path) -> None:
    changed = set(_git_lines(root, "diff", "--name-only", BASE_COMMIT, "--"))
    untracked = set(_git_lines(root, "ls-files", "--others", "--exclude-standard"))
    observed = changed | untracked
    unexpected = sorted(path for path in observed if not _allowed_change(path))
    _require(not unexpected, f"out-of-scope changed paths: {unexpected}")
    forbidden_new = sorted(
        path
        for path in observed
        if path.lower().endswith((".md", ".json"))
    )
    _require(not forbidden_new, f"new Markdown or JSON audit files: {forbidden_new}")


def validate_external_identification_audit(
    repository_root: Path | None = None,
    *,
    check_worktree: bool = True,
) -> dict[str, Any]:
    root = (
        repository_root.resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    protocol = _load_yaml(root / PROTOCOL_RELATIVE)
    prompt = _load_yaml(root / PROMPT_RELATIVE)
    reviews = [_load_yaml(root / relative) for relative in RAW_RELATIVES]
    reconciliation = _load_yaml(root / AUDIT_RELATIVE / "reconciliation.yaml")

    _validate_commit_freezes(root)
    _validate_protocol(protocol)
    _validate_raw_reviews(protocol, prompt, reviews)
    adjudications = _validate_reconciliation(protocol, reviews, reconciliation)
    papers = _validate_paper_records(root, protocol, reviews, adjudications)
    _validate_cross_paper(root, protocol, papers)
    _validate_table_data(root, protocol, papers)
    _validate_generic_comparison(root, protocol)
    _validate_provenance(root)
    if check_worktree:
        _validate_worktree_scope(root)

    agreement = reconciliation["AGREEMENT"]
    return {
        "VALID": True,
        "PAPERS": len(papers),
        "CRITERIA": len(_criteria(protocol)),
        "RATING_CELLS": len(papers) * len(_criteria(protocol)),
        "RAW_EXACT_AGREEMENT_COUNT": agreement["EXACT_AGREEMENT_COUNT"],
        "RAW_EXACT_AGREEMENT_PERCENT": agreement["EXACT_AGREEMENT_PERCENT"],
        "RAW_DISAGREEMENT_COUNT": agreement["DISAGREEMENT_COUNT"],
        "ADJUDICATIONS": len(adjudications),
        "NOVELTY_STRESS_TEST": "FRAMEWORK_PARTIALLY_DISTINCTIVE",
        "EVALUATED_MODEL_RUNS": 0,
        "GPU_USE": 0,
        "UNSEEN_CONFIRMATORY_TARGETS_SCREENED": 0,
    }


def main() -> int:
    result = validate_external_identification_audit()
    for key, value in result.items():
        print(f"{key}: {str(value).lower() if isinstance(value, bool) else value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
