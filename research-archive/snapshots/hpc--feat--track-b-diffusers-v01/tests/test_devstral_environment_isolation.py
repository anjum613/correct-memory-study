from __future__ import annotations

import json
from pathlib import Path
import subprocess

from cmpilot.devstral_profile import (
    AGENT_ENVIRONMENT_PATH,
    AGENT_PYTHON,
    CANDIDATE_AGENT_FREEZE,
    CANDIDATE_AGENT_FREEZE_SHA256,
    CANDIDATE_FREEZE,
    CANDIDATE_FREEZE_SHA256,
    CANDIDATE_LOCK,
    CANDIDATE_LOCK_SHA256,
    CANDIDATE_PACKAGE_VERSIONS,
    CANDIDATE_PYTHON_VERSION,
    ENVIRONMENT_PATH,
    MODEL_SNAPSHOT,
    SERVER_PYTHON,
    validate_candidate_environment,
)
from cmpilot.qualification import MODEL_SNAPSHOT as QWEN_MODEL_SNAPSHOT
from cmpilot.qualification import VLLM_PYTHON as QWEN_VLLM_PYTHON


ROOT = Path(__file__).parents[1]


def test_devstral_paths_are_isolated_from_validated_qwen_runtime() -> None:
    assert SERVER_PYTHON != QWEN_VLLM_PYTHON
    assert ENVIRONMENT_PATH != QWEN_VLLM_PYTHON.parent.parent
    assert MODEL_SNAPSHOT != QWEN_MODEL_SNAPSHOT
    assert "devstral" in str(ENVIRONMENT_PATH).lower()
    assert "Devstral-Small-2507" in str(MODEL_SNAPSHOT)
    assert AGENT_PYTHON.parent.parent == AGENT_ENVIRONMENT_PATH
    assert AGENT_PYTHON != QWEN_VLLM_PYTHON
    assert "devstral" in str(AGENT_ENVIRONMENT_PATH).lower()


def test_direct_candidate_pins_are_exact_and_mismatches_fail() -> None:
    candidate = dict(CANDIDATE_PACKAGE_VERSIONS)

    assert validate_candidate_environment(
        python_version=CANDIDATE_PYTHON_VERSION,
        package_versions=candidate,
    ) == ()
    errors = validate_candidate_environment(
        python_version="3.12.8",
        package_versions={**candidate, "vllm": "0.6.1.post2"},
    )
    assert "python: expected 3.11.11, found 3.12.8" in errors
    assert "vllm: expected 0.10.0, found 0.6.1.post2" in errors


def test_candidate_lock_contains_only_the_recorded_direct_pins() -> None:
    lock = ROOT / CANDIDATE_LOCK
    import hashlib

    assert hashlib.sha256(lock.read_bytes()).hexdigest() == CANDIDATE_LOCK_SHA256
    requirements = {
        line.split("==", 1)[0]: line.split("==", 1)[1]
        for line in lock.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert requirements == dict(CANDIDATE_PACKAGE_VERSIONS)


def test_exact_transitive_freezes_are_hash_bound() -> None:
    import hashlib

    assert hashlib.sha256((ROOT / CANDIDATE_FREEZE).read_bytes()).hexdigest() == (
        CANDIDATE_FREEZE_SHA256
    )
    assert hashlib.sha256(
        (ROOT / CANDIDATE_AGENT_FREEZE).read_bytes()
    ).hexdigest() == CANDIDATE_AGENT_FREEZE_SHA256


def test_environment_verifier_accepts_only_the_frozen_complete_snapshot() -> None:
    completed = subprocess.run(
        (str(SERVER_PYTHON), str(ROOT / "scripts/verify_devstral_environment.py")),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        timeout=900,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "READY"
    assert result["production_ready"] is True
    assert result["candidate_environment_matches"] is True
    assert result["checks"]["staged_metadata_hashes_match"] is True
    assert result["checks"]["server_live_freeze_matches"] is True
    assert result["checks"]["agent_live_freeze_matches"] is True
    assert result["checks"]["environment_fingerprint_matches"] is True
    assert result["checks"]["environment_content_digest_matches"] is True
    assert result["checks"]["alternative_shard_index_matches"] is True
    assert result["checks"]["tokenizer_identity"] is True
    assert result["checks"]["chat_template"] is True
    assert result["checks"]["snapshot_required_files_exist"] is True
    assert result["checks"]["runtime_weight_identity"] is True
    assert result["checks"]["snapshot_identity_frozen"] is True
    assert result["snapshot_freeze"]["status"] == "READY"
    assert result["snapshot_files"]["consolidated.safetensors"] is True
    assert result["alternative_index"]["present_shards"] == 0
