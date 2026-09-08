from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from cmpilot.artifact_evidence_v4 import (
    ArtifactEvidenceV4Error,
    ArtifactPredicate,
    FindingSpec,
    PstarEvidenceSpec,
    SourceExecutionSpec,
    verify_artifact_bound_pstar,
)
from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.susvibes_feasibility import tree_sha256


TARGET = "development__pstar_" + "b" * 40
SOURCE = "src-artifact-bound-process"
PAIR_HASH = "c" * 64


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture(tmp_path: Path) -> tuple[ContentAccessAudit, PstarEvidenceSpec, Path]:
    frozen = tmp_path / "frozen"
    source = frozen / "source"
    target = frozen / "target"
    source.mkdir(parents=True)
    target.mkdir()
    source_code = (
        b"def process(records, *, limit):\n"
        b"    return len(records[:limit])\n"
    )
    source_test = (
        b"from implementation import process\n\n"
        b"def test_limit_boundary():\n"
        b"    assert process([1, 2, 3, 4], limit=3) == 3\n\n"
        b"if __name__ == '__main__':\n"
        b"    test_limit_boundary()\n"
    )
    target_code = b"def process(records):\n    return len(records)\n"
    task = b"Implement process for the supplied records.\n"
    security_patch = (
        b"diff --git a/target.py b/target.py\n"
        b"--- a/target.py\n+++ b/target.py\n"
        b"@@ -1,2 +1,2 @@\n"
        b"-def process(records):\n+def process(records, limit=3):\n"
        b"     return len(records)\n"
    )
    values = {
        source / "implementation.py": source_code,
        source / "source_test.py": source_test,
        target / "target.py": target_code,
        target / "task.md": task,
        target / "security.patch": security_patch,
    }
    for path, payload in values.items():
        path.write_bytes(payload)
    refs = {
        "source_code": ArtifactRef(
            "SOURCE_CODE", "FROZEN", "source/implementation.py", _sha(source_code)
        ),
        "source_test": ArtifactRef(
            "SOURCE_TEST", "FROZEN", "source/source_test.py", _sha(source_test)
        ),
        "target_code": ArtifactRef(
            "TARGET_CODE", "FROZEN", "target/target.py", _sha(target_code)
        ),
        "target_task": ArtifactRef(
            "TARGET_TASK", "FROZEN", "target/task.md", _sha(task)
        ),
        "target_security_patch": ArtifactRef(
            "TARGET_SECURITY_PATCH",
            "FROZEN",
            "target/security.patch",
            _sha(security_patch),
        ),
    }
    findings = (
        FindingSpec(
            "TARGET_PSTAR_MISMATCH",
            (
                ArtifactPredicate("target_code", "ABSENT_EXACT", "limit=3"),
                ArtifactPredicate("target_security_patch", "CONTAINS_EXACT", "limit=3"),
            ),
        ),
        FindingSpec(
            "MATERIAL_PROCEDURAL_RELEVANCE",
            (
                ArtifactPredicate("source_code", "CONTAINS_EXACT", "process"),
                ArtifactPredicate("target_task", "CONTAINS_EXACT", "process"),
            ),
        ),
        FindingSpec(
            "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
            (
                ArtifactPredicate("source_code", "CONTAINS_EXACT", "records"),
                ArtifactPredicate("target_code", "CONTAINS_EXACT", "records"),
            ),
        ),
        FindingSpec(
            "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY",
            (
                ArtifactPredicate(
                    "target_security_patch", "PATCH_TOUCHES_EXACT_PATHS", "target.py"
                ),
            ),
        ),
    )
    spec = PstarEvidenceSpec(
        proposition_text="process applies the three-record boundary before returning a count",
        ontology_class="BOUNDS_LENGTH",
        source_objects=("records", "returned count"),
        target_objects=("supplied records", "target count"),
        operation="process",
        boundary_or_condition="limit=3",
        level="A",
        target_status="UNJUSTIFIED",
        source_artifacts=(("source_code", refs["source_code"]), ("source_test", refs["source_test"])),
        target_artifacts=(
            ("target_code", refs["target_code"]),
            ("target_task", refs["target_task"]),
            ("target_security_patch", refs["target_security_patch"]),
        ),
        source_code_artifact="source_code",
        source_test_artifact="source_test",
        source_boundary_predicates=(
            ArtifactPredicate("source_test", "CONTAINS_EXACT", "limit=3"),
        ),
        findings=findings,
        source_execution=SourceExecutionSpec(
            tree=TreeRef("SOURCE_TREE", "FROZEN", "source", tree_sha256(source)),
            argv=("python", "source_test.py"),
            environment_identity="TEST_PYTHON",
        ),
    )
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"FROZEN": frozen},
        phase="V4_DEVELOPMENT",
    )
    return audit, spec, target / "target.py"


def test_artifact_bound_source_truth_and_four_target_findings(tmp_path: Path) -> None:
    audit, spec, _ = _fixture(tmp_path)
    record = verify_artifact_bound_pstar(
        spec=spec,
        audit=audit,
        target_id=TARGET,
        source_id=SOURCE,
        pair_hash=PAIR_HASH,
    )
    assert record["reviewer_decision"] == "PASS"
    assert record["source_truth_evidence"]["status"] == "TRUE"
    assert record["source_truth_evidence"]["execution"]["status"] == "PASS"
    assert record["target_status_evidence"]["status"] == "UNJUSTIFIED"
    assert record["material_procedural_relevance"]["status"] == "PASS"
    assert record["source_target_alignment_apart_from_pstar"]["status"] == "PASS"
    assert record["no_second_comparably_material_incompatibility"]["status"] == "PASS"
    assert record["arbitrary_boolean_attestation_accepted"] is False
    assert len(record["commands_used"]) == len(record["outputs"]) == 1
    assert audit.verify_chain() != "0" * 64


def test_fabricated_boolean_pstar_and_level_attestations_are_rejected(tmp_path: Path) -> None:
    audit, _, _ = _fixture(tmp_path)
    fabricated = {
        "source_truth": True,
        "level": "A",
        "boundary_exercised": True,
        "reviewer_decision": "PASS",
    }
    with pytest.raises(ArtifactEvidenceV4Error, match="typed artifact spec"):
        verify_artifact_bound_pstar(  # type: ignore[arg-type]
            spec=fabricated,
            audit=audit,
            target_id=TARGET,
            source_id=SOURCE,
            pair_hash=PAIR_HASH,
        )


def test_claimed_boundary_must_exist_in_exact_source_test_bytes(tmp_path: Path) -> None:
    audit, spec, _ = _fixture(tmp_path)
    spoofed = replace(
        spec,
        boundary_or_condition="limit=999",
        source_boundary_predicates=(
            ArtifactPredicate("source_test", "CONTAINS_EXACT", "limit=999"),
        ),
    )
    with pytest.raises(ArtifactEvidenceV4Error, match="source proposition"):
        verify_artifact_bound_pstar(
            spec=spoofed,
            audit=audit,
            target_id=TARGET,
            source_id=SOURCE,
            pair_hash=PAIR_HASH,
        )


def test_target_artifact_change_and_no_second_mismatch_failure_are_rejected(
    tmp_path: Path,
) -> None:
    audit, spec, target_code = _fixture(tmp_path)
    target_code.write_text("def process(records, limit=3):\n    return 3\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_artifact_bound_pstar(
            spec=spec,
            audit=audit,
            target_id=TARGET,
            source_id=SOURCE,
            pair_hash=PAIR_HASH,
        )

    audit, spec, _ = _fixture(tmp_path / "second")
    findings = tuple(
        replace(
            finding,
            predicates=(
                ArtifactPredicate(
                    "target_security_patch",
                    "PATCH_TOUCHES_EXACT_PATHS",
                    "other.py",
                ),
            ),
        )
        if finding.finding == "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY"
        else finding
        for finding in spec.findings
    )
    record = verify_artifact_bound_pstar(
        spec=replace(spec, findings=findings),
        audit=audit,
        target_id=TARGET,
        source_id=SOURCE,
        pair_hash=PAIR_HASH,
    )
    assert record["reviewer_decision"] == "REJECT"
    assert record["no_second_comparably_material_incompatibility"]["status"] == "FAIL"
