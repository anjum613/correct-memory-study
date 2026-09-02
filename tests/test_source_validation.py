from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.source_pairing import source_feature_record, stable_record_hash
from cmpilot.source_validation import (
    SOURCE_ENTRY_REQUIRED_FIELDS,
    SealedPairLocator,
    SourceValidationError,
    classify_command_result,
    corpus_manifest_hash,
    git_repository_evidence,
    run_evidence_command,
    source_tree_evidence,
    validate_focal_safety,
    validate_source_entry,
    validate_timestamp,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


def _command_result(classification: str = "PASS") -> dict:
    environment = {"runtime": "test"}
    stdout = "ok\n"
    return {
        "command": ["python", "-c", "pass"],
        "working_directory_role": "PINNED_SOURCE_MATERIALIZATION",
        "environment": environment,
        "environment_sha256": stable_record_hash(environment),
        "started_at_utc": "2026-09-02T00:00:00+00:00",
        "finished_at_utc": "2026-09-02T00:00:01+00:00",
        "runtime_seconds": 1.0,
        "timeout_seconds": 30,
        "timed_out": classification == "INFRASTRUCTURE_INVALID",
        "exit_code": 0 if classification == "PASS" else 1,
        "stdout_utf8": stdout,
        "stderr_utf8": "",
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "classification": classification,
    }


def _pstar() -> dict:
    return {
        "ontology_class": "VALIDATION_BEFORE_USE",
        "proposition": "Every decoded value has passed verify(value).",
        "observable_objects": ["encoded value", "decoded value"],
        "operation": "decode",
        "quantifier_or_boundary": "for every decoded value",
        "verification_method": "upstream executable boundary test",
        "source_truth": True,
        "target_truth": "UNJUSTIFIED",
    }


def _focal(level: str = "A") -> dict:
    return {
        "classification": "PASS",
        "level": level,
        "pstar": _pstar(),
        "evidence_command": ["python", "-m", "pytest", "tests/test_decode.py"],
        "evidence_paths": ["tests/test_decode.py"],
        "evidence_hashes": {"tests/test_decode.py": "a" * 64},
        "derived_without_target_oracle": True,
        "scope": "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY",
    }


def _entry() -> dict:
    environment = {"container_manifest": "sha256:" + "1" * 64}
    features = source_feature_record("def decode(value):\n    return verify(value)\n", "decode value")
    value = {
        "source_id": "src-example-decode",
        "source_tier": "S2",
        "repository_url": "https://github.com/example/project.git",
        "repository_commit": "1" * 40,
        "commit_timestamp": "2020-01-01T00:00:00+00:00",
        "commit_timestamp_epoch": 1,
        "license": {"spdx": "MIT", "path": "LICENSE", "sha256": "2" * 64},
        "language": "python",
        "build_system": ["pyproject.toml"],
        "environment": environment,
        "source_task_description": "decode value",
        "source_task_provenance": {
            "kind": "UPSTREAM_TEST",
            "path": "tests/test_decode.py",
            "symbol": "test_decode",
            "sha256": "3" * 64,
        },
        "source_file": "project/decode.py",
        "source_symbol": "decode",
        "source_implementation_or_patch": "def decode(value):\n    return verify(value)\n",
        **features,
        "source_test_paths": ["tests/test_decode.py"],
        "source_test_command": ["python", "-m", "pytest", "tests/test_decode.py"],
        "source_test_result": "PASS",
        "source_build": _command_result(),
        "source_task_test": _command_result(),
        "focal_source_safety": _focal(),
        "source_environment_hash": stable_record_hash(environment),
        "source_artifact_hashes": {
            "source_file": "4" * 64,
            "source_implementation": "5" * 64,
            "source_test": "3" * 64,
        },
        "available_before_target_B": {DEVELOPMENT_IDS[0]: True},
        "reconstruction": {
            "fetch_command": ["git", "fetch", "origin", "1" * 40],
            "checkout_command": ["git", "checkout", "--detach", "1" * 40],
            "tree_sha256": "6" * 64,
            "git_tree_object_sha1": "7" * 40,
        },
    }
    assert set(value) == SOURCE_ENTRY_REQUIRED_FIELDS
    return value


def test_command_classification_separates_infrastructure_and_semantics() -> None:
    assert classify_command_result(
        exit_code=0, timed_out=False, stdout=b"ok", stderr=b""
    ) == "PASS"
    assert classify_command_result(
        exit_code=1, timed_out=False, stdout=b"assert 1 == 2", stderr=b""
    ) == "FAIL"
    assert classify_command_result(
        exit_code=1,
        timed_out=False,
        stdout=b"",
        stderr=b"No module named pytest",
    ) == "INFRASTRUCTURE_INVALID"
    assert classify_command_result(
        exit_code=-15, timed_out=True, stdout=b"", stderr=b""
    ) == "INFRASTRUCTURE_INVALID"


def test_evidence_command_preserves_outputs_hashes_runtime_and_environment(
    tmp_path: Path,
) -> None:
    descriptor = {"python": sys.version.split()[0], "role": "unit-test"}
    result = run_evidence_command(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        cwd=tmp_path,
        environment_descriptor=descriptor,
        timeout_seconds=10,
    )
    assert result["classification"] == "PASS"
    assert result["stdout_utf8"] == "out\n"
    assert result["stderr_utf8"] == "err\n"
    assert result["environment_sha256"] == stable_record_hash(descriptor)
    assert result["runtime_seconds"] >= 0


def test_git_repository_evidence_requires_exact_clean_commit_and_remote(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Test"], check=True
    )
    (repository / "source.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "source.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-qm", "source"], check=True
    )
    url = "https://github.com/example/project.git"
    subprocess.run(["git", "-C", str(repository), "remote", "add", "origin", url], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    evidence = git_repository_evidence(repository, expected_url=url, expected_commit=commit)
    assert evidence["repository_commit"] == commit
    (repository / "source.py").write_text("value = 2\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="dirty"):
        git_repository_evidence(repository, expected_url=url, expected_commit=commit)


def test_timestamp_rule_is_not_relaxed() -> None:
    validate_timestamp(100, 100)
    validate_timestamp(99, 100)
    with pytest.raises(SourceValidationError, match="later"):
        validate_timestamp(101, 100)


def test_source_entry_schema_and_focal_safety_are_fail_closed() -> None:
    entry = _entry()
    validate_source_entry(entry, confirmatory=True)
    missing = dict(entry)
    missing.pop("license")
    with pytest.raises(SourceValidationError, match="schema mismatch"):
        validate_source_entry(missing, confirmatory=True)
    static = copy.deepcopy(entry)
    static["focal_source_safety"]["level"] = "D"
    with pytest.raises(SourceValidationError, match="static-only"):
        validate_source_entry(static, confirmatory=True)
    validate_source_entry(static, confirmatory=False)


def test_focal_safety_cannot_use_target_oracle_or_global_claim() -> None:
    value = _focal()
    value["derived_without_target_oracle"] = False
    with pytest.raises(SourceValidationError, match="oracle"):
        validate_focal_safety(value, confirmatory=True)
    value = _focal()
    value["scope"] = "GLOBALLY_SECURE"
    with pytest.raises(SourceValidationError, match="overstated"):
        validate_focal_safety(value, confirmatory=True)


def test_source_tree_evidence_is_stable(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    first = source_tree_evidence(tmp_path)
    second = source_tree_evidence(tmp_path)
    assert first == second
    assert first["file_count"] == 1


def test_sealed_locator_rejects_unseen_traversal_and_symlinks(tmp_path: Path) -> None:
    sealed = tmp_path / "sealed"
    target = sealed / DEVELOPMENT_IDS[0]
    target.mkdir(parents=True)
    locator = SealedPairLocator(sealed)
    assert locator.resolve_development_target(DEVELOPMENT_IDS[0]) == target.resolve()
    with pytest.raises(PermissionError, match="development"):
        locator.resolve_development_target("../../unseen")
    link_name = DEVELOPMENT_IDS[1]
    (sealed / link_name).symlink_to(target, target_is_directory=True)
    with pytest.raises(PermissionError, match="real directory"):
        locator.resolve_development_target(link_name)


def test_corpus_hash_is_order_invariant_but_content_sensitive() -> None:
    first = _entry()
    second = copy.deepcopy(first)
    second["source_id"] = "src-example-other"
    assert corpus_manifest_hash([first, second]) == corpus_manifest_hash([second, first])
    changed = copy.deepcopy(second)
    changed["source_symbol"] = "other"
    assert corpus_manifest_hash([first, second]) != corpus_manifest_hash([first, changed])
