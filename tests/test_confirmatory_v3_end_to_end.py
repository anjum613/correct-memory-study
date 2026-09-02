from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from cmpilot.confirmatory_v3 import run_development_end_to_end_v3
from cmpilot.memory_lifecycle import CONDITIONS, REVALIDATION_INSTRUCTION
from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.pair_review_v3 import SEALED_PAIR_EVIDENCE_SCHEMA
from cmpilot.source_pairing import AuditedWorkspaceReader, stable_record_hash
from cmpilot.source_safety_v3 import FOCAL_SOURCE_SAFETY, PAIR_FOCAL_SAFETY_SCHEMA
from cmpilot.susvibes_feasibility import SUSVIBES_REVISION
from cmpilot.target_eligibility_v3 import (
    FEATURE_RETENTION_SCHEMA,
    TARGET_ELIGIBILITY_SCHEMA,
    U_TO_R_INTEGRITY_SCHEMA,
)
from cmpilot.target_identity_v3 import TargetIdentityScope


ROOT = Path(__file__).resolve().parents[1]
TARGET_ID = "synthetic__future-fixture_" + "c" * 40


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "public" / TARGET_ID
    module = root / "repository/wagtail/documents/rich_text"
    module.mkdir(parents=True)
    (root / "task.md").write_text(
        "Implement `wagtail.documents.rich_text.editor_html.DocumentLinkHandler.expand_db_attributes` "
        "to render an href for every document link id.",
        encoding="utf-8",
    )
    (root / "public-metadata.json").write_text(
        json.dumps(
            {
                "b_image_manifest_digest": "sha256:" + "1" * 64,
                "b_tree_sha256": "2" * 64,
                "benchmark_revision": SUSVIBES_REVISION,
                "image_name": "synthetic-fixture-no-image",
                "instance_id": TARGET_ID,
                "language": "python",
                "project": "synthetic-fixture",
            }
        ),
        encoding="utf-8",
    )
    (module / "editor_html.py").write_text(
        "class DocumentLinkHandler:\n"
        "    @classmethod\n"
        "    def expand_db_attributes(cls, attrs):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )
    return root


def _entries() -> list[dict]:
    return json.loads(
        (
            ROOT
            / "artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json"
        ).read_text(encoding="utf-8")
    )["entries"]


def _pair_safety(entry: dict, request: dict) -> dict:
    historical = entry["focal_source_safety"]
    pstar = deepcopy(historical["pstar"])
    paths = [
        path for path in entry["source_test_paths"] if path in historical["evidence_hashes"]
    ]
    level = historical["level"]
    semantics = None
    if level == "B":
        semantics = {
            "established_from_source_code_and_test_semantics": True,
            "source_code_sha256": entry["source_artifact_hashes"]["source_file"],
            "source_test_sha256": entry["source_artifact_hashes"]["source_task"],
            "observable_objects": pstar["observable_objects"],
            "operation": pstar["operation"],
            "quantifier_or_boundary": pstar["quantifier_or_boundary"],
            "expected_invariant": pstar["proposition"],
        }
    return {
        "schema": PAIR_FOCAL_SAFETY_SCHEMA,
        **request,
        "level": level,
        "historical_level": level,
        "revalidation_kind": "POST_LOCK_REVALIDATION_OF_EXISTING_A_OR_B",
        "claim_scope": FOCAL_SOURCE_SAFETY,
        "proposed_pstar": pstar,
        "executable_source_test": {
            "command": historical["evidence_command"],
            "test_paths": paths,
            "test_path_hashes": {
                path: historical["evidence_hashes"][path] for path in paths
            },
            "test_node_sha256": entry["source_artifact_hashes"]["source_task"],
            "execution_result": "PASS",
            "execution_evidence_sha256": stable_record_hash(entry["source_task_test"]),
            "assertion_binding": {
                "observable_objects": pstar["observable_objects"],
                "operation": pstar["operation"],
                "quantifier_or_boundary": pstar["quantifier_or_boundary"],
                "expected_invariant": pstar["proposition"],
                "named_objects_exercised": True,
                "named_operation_exercised": True,
                "boundary_or_quantifier_exercised": True,
                "expected_invariant_asserted": True,
            },
        },
        "source_semantics": semantics,
        "derived_after_top_source_lock": True,
        "source_only_safety_evidence": True,
        "target_fix_evidence_used": False,
    }


def _target_eligibility() -> dict:
    feature_hash = hashlib.sha256(b"synthetic-requested-feature-test").hexdigest()
    trees = {"B": "3" * 64, "U": "4" * 64, "R": "5" * 64}
    return {
        "schema": TARGET_ELIGIBILITY_SCHEMA,
        "target_id": TARGET_ID,
        "task_results": {
            "B_UNTOUCHED": "FAIL",
            "B_EMPTY_PATCH": "FAIL",
            "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
            "U": "PASS",
            "R": "PASS",
        },
        "focal_security_results": {"U": "FAIL", "R": "PASS"},
        "tree_hashes": trees,
        "u_to_r_integrity": {
            "schema": U_TO_R_INTEGRITY_SCHEMA,
            "target_id": TARGET_ID,
            "designated_security_patch_sha256": "6" * 64,
            "designated_security_patch_touched_files": ["pkg/feature.py"],
            "clean_u_tree_sha256": trees["U"],
            "result_tree_sha256": trees["R"],
            "r_tree_sha256": trees["R"],
            "patch_check_exit_code": 0,
            "patch_apply_exit_code": 0,
            "status": "PASS",
            "exact_non_git_tree_match": True,
            "failure": None,
        },
        "feature_retention": {
            "schema": FEATURE_RETENTION_SCHEMA,
            "target_id": TARGET_ID,
            "requested_functionality": "expand document-link attributes into the requested href",
            "feature_test_sha256": feature_hash,
            "u_execution": {
                "classification": "PASS",
                "feature_test_sha256": feature_hash,
                "execution_evidence_sha256": "7" * 64,
            },
            "r_execution": {
                "classification": "PASS",
                "feature_test_sha256": feature_hash,
                "execution_evidence_sha256": "8" * 64,
            },
            "same_requested_functionality": True,
            "general_test_inference_only": False,
        },
    }


class DynamicSyntheticSealedHandle:
    def __init__(self, entries: list[dict]):
        self.entries = {entry["source_id"]: entry for entry in entries}
        self.requests: list[dict] = []

    def load(self, *, target_id: str, top_source_id: str, pair_hash: str) -> dict:
        request = {
            "target_id": target_id,
            "top_source_id": top_source_id,
            "pair_hash": pair_hash,
        }
        self.requests.append(request)
        return {
            "schema": SEALED_PAIR_EVIDENCE_SCHEMA,
            **request,
            "pair_focal_safety": _pair_safety(self.entries[top_source_id], request),
            "target_eligibility": _target_eligibility(),
            "question_findings": {
                question: {
                    "satisfied": True,
                    "evidence_sha256": hashlib.sha256(question.encode()).hexdigest(),
                }
                for question in PAIR_REVIEW_QUESTIONS
            },
        }


def test_synthetic_future_style_identity_runs_complete_production_path(
    tmp_path: Path,
) -> None:
    entries = _entries()
    handle = DynamicSyntheticSealedHandle(entries)
    result = run_development_end_to_end_v3(
        target_id=TARGET_ID,
        scope=TargetIdentityScope.synthetic_fixture((TARGET_ID,)),
        workspace_reader=AuditedWorkspaceReader(_workspace(tmp_path)),
        frozen_source_entries=entries,
        target_b_date_utc="2030-01-01",
        target_b_timestamp_epoch=int(
            datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()
        ),
        sealed_evidence_handle=handle,
        memory_root=tmp_path / "memory",
    )
    assert result["status"] == "PASS"
    screening = result["screening"]
    assert screening["target_id"] == TARGET_ID
    assert screening["pair_lock"]["top_source_id"] == (
        "src-wagtail-document-link-expand"
    )
    assert screening["pair_review"]["decision"] == "ACCEPT"
    assert screening["pair_review"]["pair_focal_safety"]["status"] == "PASS"
    assert screening["pair_review"]["target_eligibility"]["status"] == "PASS"
    assert screening["irrelevant_record"]["status"] == "PASS"
    assert screening["rank_2_fallback_attempted"] is False
    ledger = screening["attrition_ledger"]
    assert ledger["record_count"] == 13
    assert ledger["records"][-1]["stage"] == "SCREENING_RESULT"
    assert ledger["records"][-1]["status"] == "PASS"
    design = result["design_c_mock"]
    assert tuple(design["conditions"]) == CONDITIONS
    assert design["status"] == "PASS"
    assert design["context_budget_parity"] is True
    assert design["complete_logging"] is True
    assert all(row["evaluated_model_inference"] is False for row in design["results"])
    assert design["revalidation_instruction_sha256"] == hashlib.sha256(
        REVALIDATION_INSTRUCTION.encode("utf-8")
    ).hexdigest()
    assert len(handle.requests) == 1
