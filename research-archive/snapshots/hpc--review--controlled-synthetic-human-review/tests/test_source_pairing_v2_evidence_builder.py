from __future__ import annotations

from scripts.build_source_pairing_v2_evidence import matcher_import_audit


def test_v2_matcher_has_no_io_capability_for_unseen_oracles() -> None:
    audit = matcher_import_audit()
    assert audit["forbidden_io_imports"] == []
    assert audit["unseen_u_r_security_artifacts_read"] == 0
    assert audit["evaluated_model_outputs_read"] == 0
