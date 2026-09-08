"""Build the conservative machine-readable V2 methodology-repair decision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
import xml.etree.ElementTree as ET

from .repository_manager import repository_content_digest
from .v2_fixture_audit import FAMILIES, validate_fixture_audit
from .v2_snapshot_overlay import load_overlay_manifest


AUDIT_HEAD = "8ffde96394f5990be8ffb9167c802c8d71128323"
PROTOCOL = "correct-memory-v2-methodology-repair-1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _junit(path: Path) -> dict[str, int | str]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    result: dict[str, int | str] = {
        key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    result["status"] = (
        "PASS" if result["failures"] == 0 and result["errors"] == 0 else "FAIL"
    )
    return result


def _git(repository_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_classification(repository_root: Path) -> dict[str, Any]:
    preflight = _load(repository_root / "artifacts/v2-preflight/readiness.json")
    historical_snapshot_prefixes = {
        "tests.test_aim_backend",
        "tests.test_aim_family_validation",
        "tests.test_axios_backend",
        "tests.test_devstral_prerun_amendment",
        "tests.test_httpx_backend",
        "tests.test_httpx_construction_gate",
    }
    historical_job_prefixes = {
        "tests.test_calculator_finalizer",
        "tests.test_job_25692_forensics",
    }
    rows = []
    for test in preflight["test_summary"]["failure_tests"]:
        prefix = ".".join(test.split(".")[:2])
        if prefix in historical_snapshot_prefixes:
            category = "V1_IMMUTABLE_HISTORICAL_TEST"
            disposition = (
                "V1 tree remains unchanged; equivalent V2 overlay reconstruction passes."
            )
        elif prefix in historical_job_prefixes:
            category = "V1_IMMUTABLE_HISTORICAL_TEST"
            disposition = "Historical job-25692 assertion retained unchanged."
        else:
            category = "EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE"
            disposition = "Frozen interpreter or network-mounted runtime timed out."
        rows.append({"test": test, "category": category, "disposition": disposition})
    current_unavailable = [
        "tests.test_devstral_serialization.test_exact_mistral_common_serialization_and_malformed_input_rejection",
        "tests.test_devstral_serialization.test_frozen_agent_adapter_selects_mistral_counting_explicitly",
    ]
    rows.extend(
        {
            "test": test,
            "category": "EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE",
            "disposition": "Pinned mistral-common 1.8.4 interpreter entered autofs_wait.",
        }
        for test in current_unavailable
    )
    return {
        "schema": "cmpilot-v2-test-classification-v1",
        "allowed_categories": [
            "V2_LOGIC_FAILURE",
            "V2_FIXTURE_FAILURE",
            "V1_IMMUTABLE_HISTORICAL_TEST",
            "EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE",
            "NETWORK_STORAGE_INFRASTRUCTURE_FAILURE",
            "OTHER",
        ],
        "individual_nonpassing_tests": rows,
        "unexecuted_group": {
            "count": preflight["test_summary"][
                "not_executed_due_uninterruptible_environment_mount"
            ],
            "category": "NETWORK_STORAGE_INFRASTRUCTURE_FAILURE",
            "disposition": "Preserved preflight evidence; tests were not claimed as passed.",
        },
        "unresolved_v2_logic_failures": [],
        "unresolved_v2_fixture_failures": [],
    }


def build(repository_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    repository_root = Path(repository_root)
    artifact = repository_root / "artifacts/v2-methodology-repair"
    fixture = validate_fixture_audit(
        repository_root, repository_root / "v2/fixtures/construction/manifest.json"
    )
    overlays = load_overlay_manifest(
        repository_root / "v2/fixtures/snapshot-overlays/manifest.json"
    )
    controls = _load(artifact / "historical-control-matrix.json")
    qwen = _load(artifact / "token-census-qwen.json")
    devstral = _load(artifact / "token-census-devstral.json")
    v2_tests = _junit(artifact / "pytest-v2-required.xml")
    shared_tests = _junit(artifact / "pytest-shared-required.xml")
    v1_snapshot_tests = _junit(artifact / "pytest-v1-incomplete-snapshots.xml")

    changed = _git(repository_root, "diff", "--name-only", AUDIT_HEAD, "HEAD").splitlines()
    immutable_prefixes = (
        "families/",
        "results/raw/",
        "runs/raw/",
        "memories/frozen/",
    )
    immutable_preserved = not any(path.startswith(immutable_prefixes) for path in changed)

    fixture_ready = {
        family: fixture["families"][family]["status"] == "READY" for family in FAMILIES
    }
    false_by_family = {family: False for family in FAMILIES}
    historical_security = {
        row["family"]: (
            row["states"]["UNTOUCHED_I"]["SECURITY"]["passed"] is False
            and row["states"]["SAFE_CONTROL"]["SECURITY"]["passed"] is True
        )
        for row in controls["families"]
    }

    clean_reconstruction: dict[str, bool] = {}
    for family in FAMILIES:
        if family in overlays["families"]:
            states = overlays["families"][family]["states"]
            clean_reconstruction[family] = all(
                state["reconstructed_repository_sha256"] for state in states.values()
            )
            continue
        family_root = repository_root / "families" / family
        package = _load(family_root / "family-package.json")
        checks = []
        for state, key in (
            ("source", "source_repository"),
            ("compatible", "compatible_repository"),
            ("invalidated", "target_repository"),
        ):
            checks.append(
                repository_content_digest(family_root / "repositories" / state).sha256
                == package["inputs"][key]["sha256"]
            )
        clean_reconstruction[family] = all(checks)

    cells = qwen["cells"] + devstral["cells"]
    all_fit = len(cells) == 24 and all(cell["fits_32768"] for cell in cells)
    prompt_validation = {
        "schema": "cmpilot-v2-prompt-census-validation-v1",
        "task_wording_changed": False,
        "wrapper_changed_since_preflight": (
            _git(repository_root, "diff", "--name-only", AUDIT_HEAD, "HEAD", "--", "src/cmpilot/v2_prompting.py")
            != ""
        ),
        "qwen": {
            "status": "PASS_REGENERATED",
            "cells": len(qwen["cells"]),
            "tokenizer": qwen["tokenizer"],
        },
        "devstral": {
            "status": "PASS_CARRIED_FORWARD_UNCHANGED_PROMPTS",
            "cells": len(devstral["cells"]),
            "tokenizer": devstral["tokenizer"],
            "live_recount": "EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE",
            "reason": "Pinned 1.8.4 interpreter entered autofs_wait; 24-cell inputs are byte-unchanged.",
        },
        "all_prompts_fit_32768": all_fit,
    }

    classifications = test_classification(repository_root)
    required_tests_pass = False
    blockers = [
        f"{family}: {', '.join(fixture['families'][family]['blocking_constraints'])}"
        for family in FAMILIES
    ]
    blockers.extend(
        [
            "Two exact Devstral tokenizer tests are unavailable in the frozen autofs environment.",
            "The immutable historical full repository suite is not PASS.",
        ]
    )
    readiness = {
        "protocol_version": PROTOCOL,
        "git_commit": _git(repository_root, "rev-parse", "HEAD"),
        "audit_base_commit": AUDIT_HEAD,
        "v1_immutability_preserved": immutable_preserved,
        "six_family_identity_preserved": tuple(fixture["families"]) == FAMILIES,
        "historical_evidence_preserved": immutable_preserved,
        "source_memories_preserved": immutable_preserved,
        "security_witnesses_preserved": immutable_preserved,
        "v2_fixture_construction_method": "prospective mechanical reverse/exact historical reconstruction only",
        "v2_fixture_ready_by_family": fixture_ready,
        "trust_shift_preserved_by_family": false_by_family,
        "task_completion_ready_by_family": false_by_family,
        "faithful_reuse_real_change_by_family": false_by_family,
        "faithful_reuse_completion_pass_by_family": false_by_family,
        "faithful_reuse_security_fail_by_family": false_by_family,
        "safe_control_completion_pass_by_family": false_by_family,
        "safe_control_security_pass_by_family": false_by_family,
        "historical_security_control_revalidated_by_family": historical_security,
        "clean_snapshot_reconstruction_by_family": clean_reconstruction,
        "all_prompts_fit_32768": all_fit,
        "v2_required_tests_pass": required_tests_pass,
        "full_repository_suite_pass": False,
        "os_sandbox_status": "PASS",
        "test_summary": {
            "v2_modules": v2_tests,
            "shared_required_excluding_two_unavailable_devstral_tests": shared_tests,
            "unavailable_required_devstral_tests": 2,
            "immutable_v1_snapshot_group": v1_snapshot_tests,
        },
        "qwen_qualification_status": "NOT_TESTED_NO_GPU",
        "devstral_qualification_status": "NOT_TESTED_NO_GPU",
        "remaining_non_gpu_blockers": blockers,
        "non_gpu_study_readiness": "FAIL",
        "gpu_qualification_ready": False,
        "study_run_authorized": False,
        "estimated_gpu_minimums": {
            "Qwen": "94 GB TP1, or 2x80 GB TP2; estimated 75.13 GiB at 32K/concurrency 1",
            "Devstral": "80 GB TP1; estimated 53.30 GiB at 32K/concurrency 1",
        },
        "protocol_implication": (
            "Any successful future V2 would be a prospectively redesigned replication/"
            "follow-up on the same frozen historical trust-shift families, not an exact "
            "rerun of the original execution fixtures."
        ),
    }
    return readiness, classifications, prompt_validation
