from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from scripts.mini_swe_smoke_evidence import finalize, gpu_evidence


ROOT = Path(__file__).parents[1]
GPU_SCRIPT = ROOT / "slurm" / "mini_swe_agent_smoke.sbatch"


def test_agent_config_has_exact_limits_without_endpoint_metadata() -> None:
    config_path = ROOT / "configs" / "agent" / "mini_swe_agent_smoke.yaml"
    contents = config_path.read_text(encoding="utf-8")

    assert "step_limit: 15" in contents
    assert "wall_time_limit_seconds: 450" in contents
    assert "timeout: 60" in contents
    assert "model_name:" not in contents
    assert "api_base:" not in contents
    assert "temperature: 0" in contents
    lowered = contents.lower()
    assert "memory" not in lowered
    assert "reference patch" not in lowered

    batch = GPU_SCRIPT.read_text(encoding="utf-8")
    for executable in ("CMPILOT_PY", "MINI_PY", "VLLM_PY", "VLLM_BIN"):
        assert f'test -x "${executable}"' in batch
    assert "UV_BIN" not in batch
    assert re.search(r"\bpip\b", batch, flags=re.IGNORECASE) is None
    assert "conda activate" not in batch
    assert "conda run" not in batch
    assert "conda info" not in batch
    assert "command -v conda" not in batch
    assert batch.count("record_installed_packages") == 4
    assert "from importlib.metadata import distributions" in batch
    assert "installed-packages-vllm.txt" in batch
    assert "installed-packages-agent.txt" in batch
    assert "installed-packages-cmpilot.txt" in batch
    assert "cp -a" not in batch
    assert "preserve-artifacts" in batch
    assert 'final_destination="$ARTIFACT_DIR/agent-run"' in batch


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


def test_job_24703_like_post_server_failure_is_not_infrastructure(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "agent-run"
    agent_dir.mkdir()
    (agent_dir / "run.json").write_text(
        json.dumps(
            {
                "final_classification": "infrastructure_failure",
                "agent_configuration": {"launches": 1},
                "agent_exit_code": 1,
                "after_test_exit_code": 1,
            }
        ),
        encoding="utf-8",
    )
    (agent_dir / "adapter-events.jsonl").write_text(
        '{"event": "agent_initialized"}\n'
        '{"event": "model_request_succeeded"}\n'
        '{"event": "model_request_failed", "classification": "http_status"}\n',
        encoding="utf-8",
    )
    (agent_dir / "classification.json").write_text(
        '{"success_checks":{"source_template_unchanged":true}}\n',
        encoding="utf-8",
    )
    (tmp_path / "server-probe.json").write_text(
        '{"status":"passed","health_http_status":200,"models_http_status":200}\n',
        encoding="utf-8",
    )
    (tmp_path / "process-cleanup.txt").write_text(
        "graceful_termination_confirmed\n"
        "no_server_process_remains\n"
        "no_agent_process_remains\n",
        encoding="utf-8",
    )

    exit_code = finalize(
        Namespace(
            artifact_dir=tmp_path,
            slurm_exit_status=1,
            agent_process_exit=3,
        )
    )
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))

    assert exit_code == 1
    assert result["classification"] == "agent_harness_failure"
    assert result["dimensions"]["infrastructure"] == "PASS"
    assert result["dimensions"]["server"] == "PASS"
    assert result["dimensions"]["agent_harness"] == "FAIL"
    assert result["dimensions"]["model_task_performance"] == "INCOMPLETE"
