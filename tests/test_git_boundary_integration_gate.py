from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
GATE_PATH = ROOT / "scripts/git_boundary_integration_gate.py"
BATCH_PATH = ROOT / "slurm/git_boundary_integration_gate.sbatch"

SPEC = importlib.util.spec_from_file_location("git_boundary_integration_gate", GATE_PATH)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_production_integration_gate_passes_locally_and_cleans_scratch(
    tmp_path: Path,
) -> None:
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    artifact = tmp_path / "artifact"

    result = GATE.run_gate(artifact, scratch_parent)

    assert result["classification"] == GATE.PASS
    assert all(result["checks"].values())
    assert result["cleanup"] == {"complete": True, "scratch_exists": False}
    assert not list(scratch_parent.iterdir())


def test_integration_batch_is_short_cpu_only_and_preserves_identity() -> None:
    source = BATCH_PATH.read_text(encoding="utf-8")

    assert "#SBATCH --partition=Virtual" in source
    assert "#SBATCH --cpus-per-task=1" in source
    assert "#SBATCH --mem=1G" in source
    assert "#SBATCH --time=00:05:00" in source
    assert "--gres" not in source
    assert "--gpus" not in source
    assert "vllm" not in source.casefold()
    assert "qwen" not in source.casefold()
    assert "/home/s224049759/environments/cmpilot-conda/bin/python3.11" in source
    assert "submitted-batch-script.sbatch" in source
    assert "production-integration-gate/jobs" in source
    assert "SHA256SUMS" in source
