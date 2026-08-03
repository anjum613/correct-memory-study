from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "slurm" / "mini_swe_adapter_preflight.sbatch"


def test_adapter_preflight_batch_is_cpu_only_and_short() -> None:
    contents = SCRIPT.read_text(encoding="utf-8")

    assert "#SBATCH --partition=Virtual" in contents
    assert "#SBATCH --cpus-per-task=1" in contents
    assert "#SBATCH --mem=2G" in contents
    assert "#SBATCH --time=00:05:00" in contents
    assert "#SBATCH --gres" not in contents
    assert "nvidia-smi" not in contents
    assert "vllm" not in contents.lower()


def test_adapter_preflight_batch_uses_absolute_interpreters_without_activation() -> None:
    contents = SCRIPT.read_text(encoding="utf-8")

    assert "CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python" in contents
    assert "MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python" in contents
    assert 'test -x "$CMPILOT_PY"' in contents
    assert 'test -x "$MINI_PY"' in contents
    assert "conda activate" not in contents
    assert "conda run" not in contents
    assert "conda info" not in contents
    assert '"$MINI_PY" -m pip' not in contents
    assert "command -v conda" not in contents


def test_adapter_preflight_batch_runs_one_exact_dummy_endpoint_preflight() -> None:
    contents = SCRIPT.read_text(encoding="utf-8")

    invocation = '"$CMPILOT_PY" -m cmpilot adapter-preflight'
    assert contents.count(invocation) == 2  # one quoted preview and one execution
    assert "dummy_base_url=http://127.0.0.1:9/v1" in contents
    assert "ADAPTER_PREFLIGHT_PASS" in contents
    assert "model_request_count" in contents
    assert "command_count" in contents
    assert "mini-swe-smoke-3/24670/agent.stderr.log" in contents
