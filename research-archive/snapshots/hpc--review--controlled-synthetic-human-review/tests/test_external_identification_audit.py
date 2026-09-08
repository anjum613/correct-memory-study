from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from scripts.build_external_identification_audit import build_paper_records, build_table_data
from scripts.validate_external_identification_audit import (
    validate_external_identification_audit,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPOSITORY_ROOT / "audits" / "external-identification-v1"


def _load(relative: str) -> dict:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    return parser.load((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def test_external_identification_audit_integrity() -> None:
    result = validate_external_identification_audit(
        REPOSITORY_ROOT,
        check_worktree=False,
    )

    assert result == {
        "VALID": True,
        "PAPERS": 6,
        "CRITERIA": 18,
        "RATING_CELLS": 108,
        "RAW_EXACT_AGREEMENT_COUNT": 91,
        "RAW_EXACT_AGREEMENT_PERCENT": 84.26,
        "RAW_DISAGREEMENT_COUNT": 17,
        "ADJUDICATIONS": 17,
        "NOVELTY_STRESS_TEST": "FRAMEWORK_PARTIALLY_DISTINCTIVE",
        "EVALUATED_MODEL_RUNS": 0,
        "GPU_USE": 0,
        "UNSEEN_CONFIRMATORY_TARGETS_SCREENED": 0,
    }


def test_derived_paper_and_table_artifacts_are_byte_stable() -> None:
    paper_paths = sorted((AUDIT_ROOT / "papers").glob("*.yaml"))
    table_path = AUDIT_ROOT / "table-data.yaml"
    before = {path: path.read_bytes() for path in [*paper_paths, table_path]}

    rebuilt_papers = build_paper_records()
    rebuilt_table = build_table_data(rebuilt_papers)

    assert sorted(rebuilt_papers) == paper_paths
    assert rebuilt_table == table_path
    assert {path: path.read_bytes() for path in before} == before


def test_claim_relative_scope_and_novelty_boundary() -> None:
    analysis = _load(
        "audits/external-identification-v1/cross-paper-analysis.yaml"
    )
    table = _load("audits/external-identification-v1/table-data.yaml")

    assert analysis["TOTAL_STATUS_COUNTS"] == {
        "ESTABLISHED": 41,
        "NOT_ESTABLISHED": 13,
        "UNDETERMINED": 2,
        "NOT_APPLICABLE": 52,
    }
    assert (
        analysis["STRONGER_ESTIMAND_REUSE"][
            "PAPERS_ESTABLISHING_ALL_18_REQUIREMENTS"
        ]
        == 0
    )
    assert analysis["NOVELTY_STRESS_TEST"]["RESULT"] == (
        "FRAMEWORK_PARTIALLY_DISTINCTIVE"
    )
    assert table["NOT_A_PREVALENCE_STUDY"] is True
    assert table["REQUIREMENTS_BY_PAPER"]["ROW_COUNT"] == 18
    assert table["REQUIREMENTS_BY_PAPER"]["COLUMN_COUNT"] == 6
