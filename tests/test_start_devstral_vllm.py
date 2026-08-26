from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from cmpilot.mini_swe_adapter import ADAPTER_SOURCE
from cmpilot.model_profiles import load_model_profile


REPOSITORY = Path(__file__).parents[1]
LAUNCHER = REPOSITORY / "scripts" / "start_devstral_vllm.sh"
PRIMARY_LAUNCHER = REPOSITORY / "scripts" / "start_vllm_smoke.sh"


def devstral_launcher_environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    profile = load_model_profile("devstral-small-2507")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured_args = tmp_path / "vllm-args.txt"
    captured_environment = tmp_path / "vllm-environment.txt"
    fake_vllm = fake_bin / "vllm"
    fake_vllm.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$CAPTURED_ARGS"\n'
        'printf "%s\\n" "$HF_HUB_OFFLINE" "$TRANSFORMERS_OFFLINE" "$VLLM_CACHE_ROOT" '
        '> "$CAPTURED_ENVIRONMENT"\n'
    )
    fake_vllm.chmod(0o755)

    shared_cache = tmp_path / "shared-cache"
    snapshot = (
        shared_cache
        / "huggingface"
        / "hub"
        / "models--mistralai--Devstral-Small-2507"
        / "snapshots"
        / profile.model_revision
    )
    snapshot.mkdir(parents=True)
    for name in ("config.json", "tekken.json", "model.safetensors.index.json"):
        (snapshot / name).write_text("{}")

    environment = os.environ.copy()
    environment.update(
        {
            "CAPTURED_ARGS": str(captured_args),
            "CAPTURED_ENVIRONMENT": str(captured_environment),
            "CMPILOT_SERVER_LOG_ROOT": str(tmp_path / "logs"),
            "CMPILOT_SHARED_CACHE_ROOT": str(shared_cache),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "VLLM_HOST": "127.0.0.1",
            "VLLM_PORT": "8123",
        }
    )
    return environment, captured_args, captured_environment


def test_devstral_launcher_uses_only_profiled_arguments_and_isolated_caches(tmp_path) -> None:
    profile = load_model_profile("devstral-small-2507")
    environment, captured_args, captured_environment = devstral_launcher_environment(tmp_path)

    subprocess.run(["bash", str(LAUNCHER)], check=True, capture_output=True, text=True, env=environment)

    arguments = captured_args.read_text().splitlines()
    assert arguments == ["serve", *profile.server_arguments, "--host", "127.0.0.1", "--port", "8123"]
    offline_hf, offline_transformers, runtime_cache = captured_environment.read_text().splitlines()
    assert offline_hf == "1"
    assert offline_transformers == "1"
    assert profile.identity in runtime_cache


def test_devstral_launcher_refuses_to_download_a_missing_snapshot(tmp_path) -> None:
    environment, captured_args, _ = devstral_launcher_environment(tmp_path)
    profile = load_model_profile("devstral-small-2507")
    missing = (
        Path(environment["CMPILOT_SHARED_CACHE_ROOT"])
        / "huggingface"
        / "hub"
        / "models--mistralai--Devstral-Small-2507"
        / "snapshots"
        / profile.model_revision
        / "tekken.json"
    )
    missing.unlink()

    result = subprocess.run(["bash", str(LAUNCHER)], capture_output=True, text=True, env=environment)

    assert result.returncode == 2
    assert "Exact offline Devstral snapshot is incomplete" in result.stderr
    assert not captured_args.exists()


def test_primary_launcher_and_shared_agent_adapter_match_baseline_hashes() -> None:
    assert hashlib.sha256(PRIMARY_LAUNCHER.read_bytes()).hexdigest() == (
        "add1c50f9a948d6b1a6f6db5ab8dabafa8cf2609688739395392612bcfe44132"
    )
    assert hashlib.sha256(ADAPTER_SOURCE.encode()).hexdigest() == (
        "ca6cb326858e49f5a563f3607ce23800b3dca321264a4d1431cbe62b10bebfcf"
    )
