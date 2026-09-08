from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "slurm" / "mini_swe_multiturn_preflight.sbatch"


def test_multiturn_batch_is_cpu_only_and_uses_absolute_interpreters() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for directive in (
        "#SBATCH --job-name=mini-swe-multiturn-check",
        "#SBATCH --partition=Virtual",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem=2G",
        "#SBATCH --time=00:05:00",
    ):
        assert directive in text
    assert "--gres" not in text
    assert "#SBATCH --partition=gpu" not in text
    assert "/home/s224049759/environments/cmpilot-conda/bin/python" in text
    assert "/home/s224049759/environments/mini-swe-agent-smoke/bin/python" in text
    assert 'test -x "$CMPILOT_PY"' in text
    assert 'test -x "$MINI_PY"' in text


def test_multiturn_batch_uses_metadata_inventory_and_exact_preflight() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "from importlib.metadata import distributions" in text
    assert re.search(r"\bpip\b", lowered) is None
    assert "conda activate" not in lowered
    assert "conda run" not in lowered
    assert "command -v conda" not in lowered
    assert "multiturn-preflight" in text
    assert "--mini-python \"$MINI_PY\"" in text
    assert "MULTITURN_ADAPTER_PREFLIGHT_PASS" in text
    assert "mini-swe-multiturn-preflight/$SLURM_JOB_ID" in text
    assert "vllm" not in lowered
