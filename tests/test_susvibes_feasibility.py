from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from cmpilot.susvibes_feasibility import (
    DEVELOPMENT_FILE_SHA256,
    DEVELOPMENT_IDS,
    IRRELEVANT_FILENAME,
    ParsedRun,
    SUSVIBES_REVISION,
    classify_official_runs,
    deterministic_irrelevant_patch,
    feature_retention_eligible,
    guard_row_access,
    load_development_ids,
    memory_leakage_findings,
    normalize_state,
    parse_count_logs,
    security_matrix_eligible,
    task_matrix_eligible,
    touched_files,
    unseen_instance_ids,
    validate_b_only_representation,
    validate_irrelevant_patch,
    validate_three_condition_runtime,
)
from cmpilot.v2_preflight import V2ContextProfile


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-susvibes-feasibility"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_susvibes_source_lock_is_exact_and_complete() -> None:
    lock = load_json(ARTIFACT_ROOT / "susvibes-source-lock.json")
    assert lock["release"]["commit_sha1"] == SUSVIBES_REVISION
    assert lock["release"]["tag"] == "v1.0"
    assert lock["dataset"]["sha256"] == "0cb5fbffe7ba59a8e16d42c293944bdd8e1e23795941a4b496ac1043722b9550"
    assert lock["dataset"]["task_count"] == 186
    assert lock["dataset"]["recommended_release_contains_186_tasks"] is True
    assert len(lock["task_metadata"]["per_instance_sha256"]) == 186
    assert lock["corpus"]["repository_count_by_project_field"] == 101
    assert lock["corpus"]["language_distribution"] == {"python": 186}
    assert lock["license"]["spdx"] == "MIT"
    for section in ("evaluation_code", "environment_code"):
        assert len(lock[section]["sha256"]) == 64
        assert lock[section]["file_count"] == len(lock[section]["file_sha256"])


def test_development_target_declaration_is_immutable() -> None:
    path = ROOT / "protocols/susvibes-development-seen-targets.txt"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == DEVELOPMENT_FILE_SHA256
    assert load_development_ids(path) == DEVELOPMENT_IDS
    manifest = load_json(ARTIFACT_ROOT / "development-set-manifest.json")
    assert tuple(row["instance_id"] for row in manifest["targets"]) == DEVELOPMENT_IDS
    assert manifest["official_sample"]["task_count"] == len(DEVELOPMENT_IDS)


def test_unseen_universe_excludes_development_and_oracle_fields() -> None:
    universe = load_json(ARTIFACT_ROOT / "unseen-target-universe.json")
    unseen = set(universe["unseen_ids"])
    assert universe["raw_task_count"] == 186
    assert universe["unseen_target_count"] == 181
    assert unseen.isdisjoint(DEVELOPMENT_IDS)
    assert len(unseen) == 181
    assert universe["enumeration_fields_read"] == ["instance_id"]
    serialized = json.dumps(universe).casefold()
    for key in ("golden_patch", "mask_patch", "security_patch", "test_patch", "cve_id", "problem_statement"):
        assert f'"{key}"' not in serialized
    guard_row_access(next(iter(unseen)), development_ids=DEVELOPMENT_IDS, fields=["instance_id"])
    with pytest.raises(PermissionError, match="enumeration-only"):
        guard_row_access(next(iter(unseen)), development_ids=DEVELOPMENT_IDS, fields=["problem_statement"])


def test_metadata_only_unseen_enumerator(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        "\n".join(
            json.dumps({"instance_id": value, "secret": "not returned"})
            for value in (*DEVELOPMENT_IDS, "unseen")
        )
        + "\n"
    )
    assert unseen_instance_ids(dataset, DEVELOPMENT_IDS) == ("unseen",)


def test_bur_state_normalization() -> None:
    row = {"instance_id": DEVELOPMENT_IDS[0], "mask_patch": "mask", "golden_patch": "gold"}
    assert normalize_state(row, "B_UNTOUCHED")["operations"] == []
    assert normalize_state(row, "B_EMPTY_PATCH")["operations"] == []
    irrelevant = normalize_state(row, "B_IRRELEVANT_PATCH")["operations"]
    assert irrelevant[0]["direction"] == "forward"
    assert irrelevant[0]["role"] == "irrelevant_documentation"
    u = normalize_state(row, "U_VULNERABLE_IMPLEMENTATION")["operations"]
    assert u == [{"patch": "mask", "direction": "reverse", "role": "restore_masked_vulnerable_feature"}]
    r = normalize_state(row, "R_SAFE_IMPLEMENTATION")["operations"]
    assert r == [{"patch": "gold", "direction": "forward", "role": "restore_secure_feature"}]


def test_five_state_task_matrix_classification() -> None:
    assert task_matrix_eligible(
        {
            "B_UNTOUCHED": "FAIL",
            "B_EMPTY_PATCH": "FAIL",
            "B_IRRELEVANT_PATCH": "FAIL",
            "U_VULNERABLE_IMPLEMENTATION": "PASS",
            "R_SAFE_IMPLEMENTATION": "PASS",
        }
    )
    assert not task_matrix_eligible(
        {
            "B_UNTOUCHED": "INFRASTRUCTURE_INVALID",
            "B_EMPTY_PATCH": "FAIL",
            "B_IRRELEVANT_PATCH": "FAIL",
            "U_VULNERABLE_IMPLEMENTATION": "PASS",
            "R_SAFE_IMPLEMENTATION": "PASS",
        }
    )


def test_official_count_parser_and_infrastructure_classification() -> None:
    handler = {
        "count": {
            "logs_checker": r"BOOT ABORT",
            "logs_parser": {"FAILED": r"(\d+) failed", "ERROR": r"(\d+) errors"},
        }
    }
    parsed = parse_count_logs(
        "2 failed, 1 errors\n",
        logs_handler=handler,
        timed_out=False,
        command_exit=1,
        runtime_started=True,
    )
    assert parsed == ParsedRun("completed", 3, 1, False, None)
    timeout = parse_count_logs(
        "", logs_handler=handler, timed_out=True, command_exit=-15, runtime_started=True
    )
    result = classify_official_runs(timeout, parsed, {"func": 0, "sec": 1})
    assert result["func"]["classification"] == "INFRASTRUCTURE_INVALID"
    assert result["sec"]["classification"] == "INFRASTRUCTURE_INVALID"
    missing_start = parse_count_logs(
        "FATAL runtime", logs_handler=handler, timed_out=False, command_exit=255, runtime_started=False
    )
    assert missing_start.status == "infrastructure_error"
    missing_dev_shm = parse_count_logs(
        """Traceback (most recent call last):
  File \"runner.py\", line 1, in <module>
FileNotFoundError: [Errno 2] No such file or directory: '/dev/shm'
""",
        logs_handler=handler,
        timed_out=False,
        command_exit=1,
        runtime_started=True,
    )
    assert missing_dev_shm.status == "infrastructure_error"
    assert missing_dev_shm.failures is None
    hostname_failure = parse_count_logs(
        "1 failed\nsocket.gaierror: [Errno -3] Temporary failure in name resolution\n",
        logs_handler=handler,
        timed_out=False,
        command_exit=1,
        runtime_started=True,
    )
    assert hostname_failure.status == "infrastructure_error"
    assert hostname_failure.failures is None


def test_security_matrix_classification() -> None:
    assert security_matrix_eligible({"B": "PASS", "U": "FAIL", "R": "PASS"})
    assert security_matrix_eligible({"B": "FAIL", "U": "FAIL", "R": "PASS"})
    assert not security_matrix_eligible({"B": "PASS", "U": "PASS", "R": "PASS"})
    assert not security_matrix_eligible({"B": "PASS", "U": "INFRASTRUCTURE_INVALID", "R": "PASS"})


def test_deterministic_irrelevant_patch_applies_and_is_documentation_only(tmp_path: Path) -> None:
    instance_id = DEVELOPMENT_IDS[0]
    first = deterministic_irrelevant_patch(instance_id)
    second = deterministic_irrelevant_patch(instance_id)
    assert first == second
    validate_irrelevant_patch(instance_id, first)
    assert touched_files(first) == (IRRELEVANT_FILENAME,)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    patch = tmp_path / "irrelevant.patch"
    patch.write_text(first)
    subprocess.run(["git", "apply", patch.name], cwd=tmp_path, check=True)
    assert (tmp_path / IRRELEVANT_FILENAME).is_file()


def test_feature_retention_requires_both_executable_passes_and_u_to_r() -> None:
    assert feature_retention_eligible(
        u_task="PASS",
        r_task="PASS",
        u_tree_sha256="u" * 64,
        r_tree_sha256="r" * 64,
        b_tree_sha256="b" * 64,
        security_patch_applies_u_to_r=True,
    )
    assert not feature_retention_eligible(
        u_task="PASS",
        r_task="FAIL",
        u_tree_sha256="u" * 64,
        r_tree_sha256="r" * 64,
        b_tree_sha256="b" * 64,
        security_patch_applies_u_to_r=True,
    )


def test_oracle_firewall_blocks_absolute_relative_and_symlink_access(tmp_path: Path) -> None:
    public = tmp_path / "targets/public/example"
    sealed = tmp_path / "oracle_sealed/example"
    public.mkdir(parents=True)
    sealed.mkdir(parents=True)
    (public / "task.md").write_text("public")
    secret = sealed / "security-test.patch"
    secret.write_text("sealed")
    (public / "absolute-link").symlink_to(secret)
    (public / "relative-link").symlink_to("../../../oracle_sealed/example/security-test.patch")
    probe = r'''
from pathlib import Path
checks = [
    Path("/workspace/../../../oracle_sealed/example/security-test.patch"),
    Path("/workspace/absolute-link"),
    Path("/workspace/relative-link"),
    Path("%s"),
]
for path in checks:
    try:
        path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        continue
    raise SystemExit(1)
assert Path("/workspace/task.md").read_text() == "public"
''' % secret
    environment = dict(os.environ)
    environment["CMPILOT_V2_SANDBOX_TMP_PARENT"] = str(tmp_path)
    result = subprocess.run(
        [
            str(ROOT / "scripts/v2_agent_sandbox.sh"),
            str(public.resolve()),
            "/opt/miniconda3/bin/python",
            "-c",
            probe,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert secret.read_text() == "sealed"


def test_b_only_representation_schema_has_no_oracle_fields() -> None:
    schema = load_json(ROOT / "schemas/b-only-target-representation.schema.json")
    artifact_schema = load_json(ARTIFACT_ROOT / "b-only-target-schema.json")
    assert schema == artifact_schema
    representation = {
        "benchmark_instance_id": "example",
        "benchmark_revision": SUSVIBES_REVISION,
        "b_snapshot_sha256": "a" * 64,
        "task_statement": "Implement session storage.",
        "language": "python",
        "repository_visible_imports": [],
        "repository_visible_libraries": [],
        "repository_visible_api_calls": [],
        "task_described_operation": "store a session",
        "visible_target_symbols": [],
        "types_and_data_roles": [],
        "ast_structure": [],
        "operation_categories": ["validation-before-use"],
        "task_semantic_embedding": None,
        "configuration_context": {},
    }
    validate_b_only_representation(representation, schema)
    representation["cve_id"] = "CVE-0000-0000"
    with pytest.raises(ValueError, match="extra fields"):
        validate_b_only_representation(representation, schema)


def test_future_memory_schema_and_leakage_gate() -> None:
    schema = load_json(ROOT / "schemas/future-memory-packet.schema.json")
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "source_task",
        "source_implementation",
        "source_validation",
    }
    clean = {
        "source_task": "Parse an existing local record.",
        "source_implementation": "def parse(value): return value.strip()",
        "source_validation": "pytest tests/test_parse.py: 1 passed",
    }
    assert memory_leakage_findings(clean) == []
    assert "cve" in memory_leakage_findings({**clean, "source_task": "CVE-2025-1234"})
    assert "packet_topology" in memory_leakage_findings({**clean, "target_fix": "x"})


def test_balanced_three_condition_runtime_configuration() -> None:
    value = load_json(ROOT / "configs/v2/susvibes-three-condition-runtime.json")
    validate_three_condition_runtime(value)
    profile = V2ContextProfile()
    assert profile.physical_context == value["runtime"]["physical_context"] == 32768
    assert profile.trajectory_budget == value["runtime"]["post_ingestion_trajectory_budget"] == 16384
    assert profile.safety_reserve == value["runtime"]["context_reserve"] == 256
    assert profile.per_turn_generation_ceiling == value["runtime"]["per_turn_generation_maximum"] == 4096
    assert profile.maximum_model_decisions == value["runtime"]["maximum_model_decisions"] == 32
    assert value["model_inference_authorized"] is False


def test_required_preoutcome_artifacts_exist() -> None:
    required = {
        "b-only-target-schema.json",
        "development-set-manifest.json",
        "future-memory-format.md",
        "source-corpus-requirements.md",
        "susvibes-schema-map.json",
        "susvibes-source-lock.json",
        "unseen-target-universe.json",
    }
    assert required <= {path.name for path in ARTIFACT_ROOT.iterdir()}
