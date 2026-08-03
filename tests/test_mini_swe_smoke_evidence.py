from __future__ import annotations

from pathlib import Path

from scripts.mini_swe_smoke_evidence import gpu_evidence


ROOT = Path(__file__).parents[1]


def test_agent_config_has_exact_limits_and_loopback_model() -> None:
    config_path = ROOT / "configs" / "agent" / "mini_swe_agent_smoke.yaml"
    contents = config_path.read_text(encoding="utf-8")

    assert "step_limit: 15" in contents
    assert "wall_time_limit_seconds: 450" in contents
    assert "timeout: 60" in contents
    assert "model_name: openai/Qwen/Qwen2.5-Coder-1.5B-Instruct" in contents
    assert "api_base: http://127.0.0.1:8000/v1" in contents
    assert "temperature: 0" in contents
    lowered = contents.lower()
    assert "memory" not in lowered
    assert "reference patch" not in lowered


def test_gpu_evidence_reports_peak_observed_memory(tmp_path: Path) -> None:
    (tmp_path / "gpu-info.txt").write_text(
        "NVIDIA RTX 4000 SFF Ada Generation, 20475, 535.288.01\n",
        encoding="utf-8",
    )
    (tmp_path / "nvidia-smi-before.txt").write_text("0MiB / 20475MiB\n", encoding="utf-8")
    (tmp_path / "nvidia-smi-serving.txt").write_text("13457MiB / 20475MiB\n", encoding="utf-8")
    (tmp_path / "nvidia-smi-after.txt").write_text("0MiB / 20475MiB\n", encoding="utf-8")

    result = gpu_evidence(tmp_path)

    assert result == {
        "name": "NVIDIA RTX 4000 SFF Ada Generation",
        "total_memory_mib": 20475,
        "driver_version": "535.288.01",
        "peak_observed_memory_mib": 13457,
    }
