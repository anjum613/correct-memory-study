from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
PROBE_PATH = ROOT / "scripts/landlock_capability_probe.py"
BATCH_PATH = ROOT / "slurm/landlock_capability_gate.sbatch"

SPEC = importlib.util.spec_from_file_location("landlock_capability_probe", PROBE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


@pytest.fixture(scope="module")
def local_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("landlock-local-gate")
    result = PROBE.run_probe(scratch_parent=root, batch_script=None)
    (root / "captured-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def test_controller_landlock_is_unprivileged_and_usable(local_result: dict) -> None:
    assert local_result["classification"] == PROBE.LANDLOCK_AVAILABLE_AND_USABLE
    assert local_result["availability"]["available"] is True
    assert local_result["availability"]["abi"] >= 1
    assert local_result["child"]["setup"]["ruleset_creation"]["success"] is True
    assert local_result["child"]["setup"]["rule_addition"]["success"] is True
    assert local_result["child"]["setup"]["restrict_self"]["success"] is True
    assert local_result["child"]["setup"]["no_new_privs"]["success"] is True
    assert local_result["user_namespace_used"] is False
    assert local_result["user_namespace_required"] is False


def test_required_access_and_inheritance_matrix_passes(local_result: dict) -> None:
    child = local_result["child"]

    assert all(item["allowed"] for item in child["allowed"].values())
    assert all(item["blocked"] for item in child["denied"].values())
    assert all(item["blocked"] for item in child["symlink_alias"].values())
    assert child["broad_traversal"]["pass"] is True
    assert child["runtime_execution_compatible"] is True
    assert all(
        child["inheritance"][name]["pass"]
        for name in ("python_child", "shell_child", "exec_child", "grandchild")
    )
    assert child["inheritance"]["middle_child_alive_after_wait"] is False


def test_parent_integrity_and_idempotent_cleanup_pass(local_result: dict) -> None:
    parent = local_result["parent_verification"]

    assert parent["denied_integrity"] is True
    assert parent["allowed_effects"] is True
    assert parent["child_reaped"] is True
    assert parent["scratch_cleanup"]["pass"] is True
    assert len(parent["scratch_cleanup"]["attempts"]) == 2
    assert not Path(parent["scratch_path"]).exists()


def test_probe_cli_writes_only_requested_output_and_cleans_scratch(
    tmp_path: Path,
) -> None:
    output = tmp_path / "artifact" / "result.json"
    scratch_parent = tmp_path / "scratch-parent"
    scratch_parent.mkdir()
    before = set(tmp_path.rglob("*"))

    completed = subprocess.run(
        [
            sys.executable,
            str(PROBE_PATH),
            "--output",
            str(output),
            "--scratch-parent",
            str(scratch_parent),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["classification"] == PROBE.LANDLOCK_AVAILABLE_AND_USABLE
    assert result["parent_verification"]["scratch_cleanup"]["pass"] is True
    assert not list(scratch_parent.iterdir())
    assert not list(output.parent.glob(".*.tmp"))
    assert set(tmp_path.rglob("*")) - before == {
        output.parent,
        output,
    }


def test_probe_records_all_known_abi_rights(local_result: dict) -> None:
    abi = local_result["availability"]["abi"]
    setup = local_result["child"]["setup"]
    expected_supported = {
        name for name, _, minimum in PROBE.KNOWN_FS_RIGHTS if abi >= minimum
    }
    expected_unsupported = {
        name for name, _, minimum in PROBE.KNOWN_FS_RIGHTS if abi < minimum
    }

    assert set(setup["supported_rights"]) == expected_supported
    assert {
        item["name"] for item in setup["unsupported_known_rights"]
    } == expected_unsupported


def test_batch_wrapper_is_short_cpu_only_and_preserves_evidence() -> None:
    source = BATCH_PATH.read_text(encoding="utf-8")

    assert "#SBATCH --partition=Virtual" in source
    assert "#SBATCH --cpus-per-task=1" in source
    assert "#SBATCH --mem=1G" in source
    assert "#SBATCH --time=00:05:00" in source
    assert "--gres" not in source
    assert "--gpus" not in source
    assert "vllm" not in source.casefold()
    assert "qwen" not in source.casefold()
    assert "/home/s224049759/environments/cmpilot-conda/bin/python" in source
    assert "submitted-batch-script.sbatch" in source
    assert "result.json" in source
    assert "SHA256SUMS" in source


def test_probe_has_no_model_or_agent_runtime_dependency() -> None:
    source = PROBE_PATH.read_text(encoding="utf-8").casefold()

    assert "miniswe" not in source
    assert "vllm" not in source
    assert "qwen" not in source
