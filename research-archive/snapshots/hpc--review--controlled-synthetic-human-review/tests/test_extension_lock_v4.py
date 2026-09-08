from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/lock_confirmatory_v4_extension.py"
SPEC = importlib.util.spec_from_file_location("lock_confirmatory_v4_extension", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SCREEN_SCRIPT = ROOT / "scripts/screen_confirmatory_v4_extension.py"
SCREEN_SPEC = importlib.util.spec_from_file_location(
    "screen_confirmatory_v4_extension", SCREEN_SCRIPT
)
assert SCREEN_SPEC is not None and SCREEN_SPEC.loader is not None
SCREEN_MODULE = importlib.util.module_from_spec(SCREEN_SPEC)
SCREEN_SPEC.loader.exec_module(SCREEN_MODULE)


def test_extension_selection_is_exactly_the_prospectively_frozen_five() -> None:
    assert MODULE.EXTENSION_IDS == (
        "vyperlang__vyper_851f7a1b3aa2a36fd041e3d0ed38f9355a58c8ae",
        "openstack__aodh_149d3ad2193b4d17df801f82a0a6be62dba564db",
        "urllib3__urllib3_a74c9cfbaed9f811e7563cfc3dce894928e0221a",
        "tensorflow__tensorflow_dbdd98c37bc25249e8f288bd30d01e118a7b4498",
        "django__django_1f2dd37f6fcefdd10ed44cb233b2e62b520afb38",
    )
    assert set(MODULE.TARGETS).issubset(MODULE.EXTENSION_IDS)
    assert SCREEN_MODULE.EXTENSION_IDS == MODULE.EXTENSION_IDS
    assert tuple(SCREEN_MODULE.TARGETS) == (MODULE.EXTENSION_IDS[0],)
    assert SCREEN_MODULE.TARGETS[MODULE.EXTENSION_IDS[0]]["pstar"] is None


def test_target_scoped_dataset_extraction_requires_one_exact_identity() -> None:
    target = MODULE.EXTENSION_IDS[0]
    other = MODULE.EXTENSION_IDS[1]
    payload = (
        json.dumps({"instance_id": other, "problem_statement": target})
        + "\n"
        + json.dumps({"instance_id": target, "problem_statement": "task"})
        + "\n"
    ).encode()
    row_bytes, row = MODULE._one_dataset_row(payload, target)
    assert json.loads(row_bytes) == row
    assert row["instance_id"] == target

    exact = (json.dumps({"instance_id": target, "problem_statement": "task"}) + "\n").encode()
    row_bytes, row = MODULE._one_dataset_row(exact, target)
    assert row_bytes == exact
    assert row["instance_id"] == target

    duplicate = exact + exact
    with pytest.raises(RuntimeError, match="exactly one"):
        MODULE._one_dataset_row(duplicate, target)


def test_target_scoped_feature_extraction_returns_only_selected_bytes() -> None:
    target = MODULE.EXTENSION_IDS[0]
    other = MODULE.EXTENSION_IDS[1]
    payload = json.dumps({other: "FROM other", target: "FROM selected"}).encode()
    selected = MODULE._one_feature(payload, target)
    assert json.loads(selected) == {target: "FROM selected"}
    assert other.encode() not in selected


def test_v4_screening_path_contains_no_evaluated_model_invocation() -> None:
    paths = (
        ROOT / "src/cmpilot/artifact_evidence_v4.py",
        ROOT / "src/cmpilot/content_audit_v4.py",
        ROOT / "src/cmpilot/production_v4.py",
        ROOT / "src/cmpilot/target_runtime_v4.py",
        SCRIPT,
        SCREEN_SCRIPT,
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "final_model_runtime",
        "vllm_client",
        "qwen",
        "devstral",
        "model.generate",
        "model.invoke",
    ):
        assert forbidden not in combined.casefold()
