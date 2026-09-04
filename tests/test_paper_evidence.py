from __future__ import annotations

from paper.validate_evidence import (
    validate_bibliography,
    validate_claim_ledger,
    validate_controls,
    validate_external_audit_tables,
    validate_human_review_packets,
    validate_identification_contract,
    validate_manuscript_claim_language,
    validate_no_scientific_mutation,
    validate_tex_sources,
    validate_v1_evidence,
    validate_v4_attrition,
)


def test_frozen_claim_ledger_and_v1_table() -> None:
    validate_claim_ledger()
    validate_v1_evidence()


def test_estimand_derived_contract_and_v4_attrition() -> None:
    validate_identification_contract()
    validate_v4_attrition()


def test_positive_and_negative_controls_match_frozen_evidence() -> None:
    validate_controls()


def test_external_tables_and_human_packets_match_frozen_ratings() -> None:
    validate_external_audit_tables()
    validate_human_review_packets()


def test_manuscript_claim_boundaries_and_bibliography() -> None:
    validate_manuscript_claim_language()
    validate_bibliography()
    validate_tex_sources()


def test_no_scientific_artifact_was_changed() -> None:
    validate_no_scientific_mutation()
