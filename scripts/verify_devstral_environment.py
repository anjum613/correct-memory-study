#!/usr/bin/env python3
"""Verify the isolated Devstral candidate environment without importing models."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import (  # noqa: E402
    AGENT_ENVIRONMENT_PATH,
    AGENT_PYTHON,
    ALTERNATIVE_SHARDS_TOTAL_SIZE,
    ALTERNATIVE_WEIGHT_SHARD_FILES,
    CANDIDATE_AGENT_FREEZE,
    CANDIDATE_AGENT_FREEZE_SHA256,
    CANDIDATE_AGENT_LOCK,
    CANDIDATE_AGENT_LOCK_SHA256,
    CANDIDATE_AGENT_PACKAGE_VERSIONS,
    CANDIDATE_FREEZE,
    CANDIDATE_FREEZE_SHA256,
    CANDIDATE_LOCK,
    CANDIDATE_LOCK_SHA256,
    ENVIRONMENT_CONTENT_DIGEST_SHA256,
    ENVIRONMENT_CONTENT_DISTRIBUTIONS,
    ENVIRONMENT_FINGERPRINT_SHA256,
    ENVIRONMENT_PATH,
    EXPECTED_CONSOLIDATED_SHA256,
    EXPECTED_CONSOLIDATED_SIZE,
    MODEL_SNAPSHOT,
    REQUIRED_SNAPSHOT_FILES,
    SERVER_PYTHON,
    STAGED_SNAPSHOT_FILE_SHA256,
    normalize_package_name,
    validate_candidate_environment,
)
from cmpilot.devstral_serialization import ExactMistralChatTokenCounter  # noqa: E402
from cmpilot.devstral_snapshot_freeze import (  # noqa: E402
    SNAPSHOT_FREEZE,
    validate_devstral_snapshot_freeze_observation,
)
from cmpilot.environment_content_digest import (  # noqa: E402
    fingerprint_installed_distributions,
)
from cmpilot.environment_fingerprint import (  # noqa: E402
    fingerprint_installed_environment,
)


PROFILE_CONFIG = ROOT / "configs/models/devstral-small-2507.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions[normalize_package_name(name)] = distribution.version
    return versions


def _command_pass(command: tuple[str, ...]) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        timeout=90,
    )
    detail = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, detail


def _requirements(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def verification_result() -> dict[str, object]:
    lock_path = ROOT / CANDIDATE_LOCK
    config = json.loads(PROFILE_CONFIG.read_text(encoding="utf-8"))
    lock_sha256 = sha256_file(lock_path) if lock_path.is_file() else None
    freeze_path = ROOT / CANDIDATE_FREEZE
    freeze_sha256 = sha256_file(freeze_path) if freeze_path.is_file() else None
    agent_lock_path = ROOT / CANDIDATE_AGENT_LOCK
    agent_lock_sha256 = (
        sha256_file(agent_lock_path) if agent_lock_path.is_file() else None
    )
    agent_freeze_path = ROOT / CANDIDATE_AGENT_FREEZE
    agent_freeze_sha256 = (
        sha256_file(agent_freeze_path) if agent_freeze_path.is_file() else None
    )
    package_errors = validate_candidate_environment(
        python_version=platform.python_version(),
        package_versions=installed_versions(),
    )
    actual_interpreter = Path(sys.executable).resolve()
    actual_prefix = Path(sys.prefix).resolve()
    expected_interpreter = SERVER_PYTHON.resolve(strict=False)
    expected_prefix = ENVIRONMENT_PATH.resolve(strict=False)
    observed_snapshot_files = {
        name: {
            "sha256": sha256_file((MODEL_SNAPSHOT / name).resolve(strict=True)),
            "size": (MODEL_SNAPSHOT / name).resolve(strict=True).stat().st_size,
        }
        for name in REQUIRED_SNAPSHOT_FILES
        if (MODEL_SNAPSHOT / name).is_file()
    }
    snapshot_files = {
        name: name in observed_snapshot_files for name in REQUIRED_SNAPSHOT_FILES
    }
    staged_hashes = {
        name: observed_snapshot_files.get(name, {}).get("sha256")
        for name, _ in STAGED_SNAPSHOT_FILE_SHA256
    }
    staged_hashes_match = staged_hashes == dict(STAGED_SNAPSHOT_FILE_SHA256)
    runtime_weight_observation = observed_snapshot_files.get(
        "consolidated.safetensors", {}
    )
    runtime_weight_size = runtime_weight_observation.get("size")
    runtime_weight_sha256 = runtime_weight_observation.get("sha256")
    runtime_weight_matches = (
        runtime_weight_size == EXPECTED_CONSOLIDATED_SIZE
        and runtime_weight_sha256 == EXPECTED_CONSOLIDATED_SHA256
    )
    index_path = MODEL_SNAPSHOT / "model.safetensors.index.json"
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    indexed_shards = tuple(sorted(set(index_data["weight_map"].values())))
    index_matches = (
        indexed_shards == ALTERNATIVE_WEIGHT_SHARD_FILES
        and index_data.get("metadata", {}).get("total_size")
        == ALTERNATIVE_SHARDS_TOTAL_SIZE
    )
    alternative_shards_present = sum(
        (MODEL_SNAPSHOT / name).is_file() for name in ALTERNATIVE_WEIGHT_SHARD_FILES
    )
    server_pip_check, server_pip_detail = _command_pass(
        (str(SERVER_PYTHON), "-m", "pip", "check")
    )
    server_freeze, server_freeze_detail = _command_pass(
        (str(SERVER_PYTHON), "-m", "pip", "freeze", "--all")
    )
    server_imports, server_import_detail = _command_pass(
        (
            str(SERVER_PYTHON),
            "-c",
            "import torch,transformers,tokenizers,mistral_common,vllm,xgrammar,outlines_core",
        )
    )
    agent_pip_check, agent_pip_detail = _command_pass(
        (str(AGENT_PYTHON), "-m", "pip", "check")
    )
    agent_freeze, agent_freeze_detail = _command_pass(
        (str(AGENT_PYTHON), "-m", "pip", "freeze", "--all")
    )
    agent_probe = (
        "from importlib.metadata import version; import json,platform,sys; "
        "import minisweagent,mistral_common; "
        f"names={tuple(name for name, _ in CANDIDATE_AGENT_PACKAGE_VERSIONS)!r}; "
        "print(json.dumps({'prefix':sys.prefix,'python':platform.python_version(),"
        "'versions':{name:version(name) for name in names}}))"
    )
    agent_imports, agent_import_detail = _command_pass(
        (str(AGENT_PYTHON), "-c", agent_probe)
    )
    agent_identity_matches = False
    if agent_imports:
        try:
            agent_result = json.loads(agent_import_detail.splitlines()[-1])
            agent_identity_matches = (
                Path(agent_result["prefix"]).resolve()
                == AGENT_ENVIRONMENT_PATH.resolve()
                and agent_result["python"] == platform.python_version()
                and agent_result["versions"]
                == dict(CANDIDATE_AGENT_PACKAGE_VERSIONS)
            )
        except (IndexError, KeyError, json.JSONDecodeError):
            agent_identity_matches = False
    tokenizer = ExactMistralChatTokenCounter(MODEL_SNAPSHOT)
    serialization = tokenizer.encode(
        [
            {"role": "system", "content": "You are exact."},
            {"role": "user", "content": "Reply with one word."},
        ]
    )
    exact_revision = (
        MODEL_SNAPSHOT.name == config["model"]["revision"]
        == config["model"]["resolved_revision"]
    )
    fingerprint = fingerprint_installed_environment()
    content_digest = fingerprint_installed_distributions(
        ENVIRONMENT_CONTENT_DISTRIBUTIONS
    )
    expected_snapshot_hashes = {
        **dict(STAGED_SNAPSHOT_FILE_SHA256),
        "consolidated.safetensors": EXPECTED_CONSOLIDATED_SHA256,
    }
    snapshot_freeze = validate_devstral_snapshot_freeze_observation(
        ROOT / SNAPSHOT_FREEZE,
        observed_snapshot_files,
        snapshot_revision=MODEL_SNAPSHOT.name,
    )
    configured_freeze = config["model"].get("snapshot_freeze")
    snapshot_identity_frozen = (
        config["model"].get("snapshot_file_sha256") == expected_snapshot_hashes
        and isinstance(configured_freeze, dict)
        and configured_freeze.get("path") == str(SNAPSHOT_FREEZE)
        and configured_freeze.get("sha256") == snapshot_freeze.freeze_sha256
        and snapshot_freeze.valid
    )
    checks = {
        "candidate_lock_matches": lock_sha256 == CANDIDATE_LOCK_SHA256,
        "candidate_freeze_matches": freeze_sha256 == CANDIDATE_FREEZE_SHA256,
        "candidate_agent_lock_matches": (
            agent_lock_sha256 == CANDIDATE_AGENT_LOCK_SHA256
        ),
        "candidate_agent_freeze_matches": (
            agent_freeze_sha256 == CANDIDATE_AGENT_FREEZE_SHA256
        ),
        "exact_environment_prefix": actual_prefix == expected_prefix,
        "exact_server_interpreter": actual_interpreter == expected_interpreter,
        "candidate_python_and_direct_pins_match": not package_errors,
        "environment_fingerprint_matches": (
            fingerprint.sha256 == ENVIRONMENT_FINGERPRINT_SHA256
            == config["environment"]["environment_fingerprint_sha256"]
        ),
        "environment_content_digest_matches": (
            content_digest.sha256 == ENVIRONMENT_CONTENT_DIGEST_SHA256
            == config["environment"]["authoritative_content_digest_sha256"]
        ),
        "server_pip_check": server_pip_check,
        "server_live_freeze_matches": server_freeze
        and server_freeze_detail.splitlines() == _requirements(freeze_path),
        "server_required_imports": server_imports,
        "agent_pip_check": agent_pip_check,
        "agent_live_freeze_matches": agent_freeze
        and agent_freeze_detail.splitlines() == _requirements(agent_freeze_path),
        "agent_required_imports_and_exact_pins": agent_identity_matches,
        "snapshot_directory_exists": MODEL_SNAPSHOT.is_dir(),
        "exact_revision": exact_revision,
        "staged_metadata_hashes_match": staged_hashes_match,
        "alternative_shard_index_matches": index_matches,
        "tokenizer_identity": tokenizer.identity["tekken_sha256"]
        == dict(STAGED_SNAPSHOT_FILE_SHA256)["tekken.json"],
        "chat_template": serialization.token_count == 14,
        "snapshot_required_files_exist": all(snapshot_files.values()),
        "runtime_weight_identity": runtime_weight_matches,
        "snapshot_identity_frozen": snapshot_identity_frozen,
    }
    candidate_environment_matches = all(
        checks[key]
        for key in (
            "candidate_lock_matches",
            "candidate_freeze_matches",
            "exact_environment_prefix",
            "exact_server_interpreter",
            "candidate_python_and_direct_pins_match",
            "environment_fingerprint_matches",
            "environment_content_digest_matches",
            "server_pip_check",
            "server_live_freeze_matches",
            "server_required_imports",
            "candidate_agent_lock_matches",
            "candidate_agent_freeze_matches",
            "agent_pip_check",
            "agent_live_freeze_matches",
            "agent_required_imports_and_exact_pins",
        )
    )
    production_ready = candidate_environment_matches and all(checks.values())
    return {
        "agent_environment_path": str(AGENT_ENVIRONMENT_PATH),
        "agent_lock_sha256": agent_lock_sha256,
        "agent_freeze_sha256": agent_freeze_sha256,
        "alternative_index": {
            "indexed_shards": list(indexed_shards),
            "indexed_total_size": index_data["metadata"]["total_size"],
            "present_shards": alternative_shards_present,
            "required_by_frozen_mistral_loader": False,
        },
        "actual_interpreter": str(actual_interpreter),
        "actual_prefix": str(actual_prefix),
        "candidate_environment_matches": candidate_environment_matches,
        "checks": checks,
        "environment_path": str(ENVIRONMENT_PATH),
        "environment_content_digest": content_digest.as_record(),
        "environment_fingerprint": fingerprint.as_record(
            interpreter=str(SERVER_PYTHON)
        ),
        "lock_sha256": lock_sha256,
        "freeze_sha256": freeze_sha256,
        "package_errors": list(package_errors),
        "production_ready": production_ready,
        "schema": "devstral-serving-environment-verification-v2",
        "server_import_detail": server_import_detail,
        "server_pip_detail": server_pip_detail,
        "agent_import_detail": agent_import_detail,
        "agent_pip_detail": agent_pip_detail,
        "staged_file_sha256": staged_hashes,
        "snapshot_files": snapshot_files,
        "runtime_weight": {
            "expected_sha256": EXPECTED_CONSOLIDATED_SHA256,
            "expected_size": EXPECTED_CONSOLIDATED_SIZE,
            "sha256": runtime_weight_sha256,
            "size": runtime_weight_size,
        },
        "snapshot_freeze": snapshot_freeze.as_record(),
        "status": "READY" if production_ready else "NOT_READY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = verification_result()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.resolve(strict=True)
        with arguments.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    sys.stdout.write(payload)
    return 0 if result["production_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
