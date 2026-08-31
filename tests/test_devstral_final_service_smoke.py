from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts import devstral_final_service_smoke as smoke


ROOT = Path(__file__).parents[1]


def test_preflight_is_no_write_and_bound_to_clean_exact_slurm_identity(
    tmp_path: Path,
) -> None:
    expected_commit = "a" * 40
    attempt = tmp_path / "slurm-123-service-smoke-v1"

    def command_runner(argv):
        if tuple(argv) == ("git", "status", "--porcelain"):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        assert tuple(argv) == ("git", "rev-parse", "HEAD")
        return subprocess.CompletedProcess(
            argv, 0, stdout=f"{expected_commit}\n", stderr=""
        )

    record = smoke.build_preflight(
        attempt_directory=attempt,
        expected_project_commit=expected_commit,
        job_id="123",
        environment={"SLURM_JOB_ID": "123"},
        command_runner=command_runner,
    )

    assert record["pass"] is True
    assert record["side_effects"] is False
    assert record["scientific_evidence"] is False
    assert not attempt.exists()


def test_smoke_uses_service_lifecycle_one_benign_request_and_shutdown(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "slurm-124-service-smoke-v1"
    calls: list[str] = []

    def write(path: Path, value: dict[str, object]) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    class FakeService:
        def start(self, *, attempt_directory, run_id, slurm_job_id):
            calls.append("start")
            assert Path(attempt_directory) == attempt
            assert run_id == smoke.SMOKE_ID
            assert slurm_job_id == "124"
            write(attempt / "gpu-allocation.json", {"pass": True})
            write(attempt / "runtime-integrity.json", {"pass": True})
            write(attempt / "server-startup.json", {"pass": True})
            write(
                attempt / "server-health.json",
                {"pass": True, "status_code": 200},
            )
            write(attempt / "server-models.json", {"pass": True})
            (attempt / "server.pid").write_text("99191\n", encoding="ascii")
            return "http://127.0.0.1:47989/v1"

        def shutdown(self):
            calls.append("shutdown")
            return {"complete": True, "pass": True}

    def request_sender(base_url: str):
        calls.append("request")
        assert base_url == "http://127.0.0.1:47989/v1"
        return (
            {"pass": True, "status_code": 200},
            {"choices": [{"message": {"content": "READY"}}]},
        )

    result = smoke.execute_smoke(
        attempt_directory=attempt,
        job_id="124",
        service_factory=FakeService,
        request_sender=request_sender,
    )

    assert calls == ["start", "request", "shutdown"]
    assert result["pass"] is True
    assert result["scientific_evidence"] is False
    assert set(result["checks"].values()) == {True}
    assert (attempt / "benign-model-request.json").is_file()
    assert (attempt / "benign-model-response.json").is_file()
    assert (attempt / "technical-smoke-result.json").is_file()


def test_batch_is_bounded_non_scientific_and_uses_final_service_smoke() -> None:
    text = (ROOT / "slurm/devstral_final_service_smoke.sbatch").read_text(
        encoding="utf-8"
    )

    assert "#SBATCH --gres=gpu:a100:2" in text
    assert "#SBATCH --time=01:00:00" in text
    assert "#SBATCH --no-requeue" in text
    assert "scripts/devstral_final_service_smoke.py" in text
    assert "--preflight-only" in text
    assert "test -x /usr/bin/nvidia-smi" in text
    assert 'test -n "${CUDA_VISIBLE_DEVICES:-}"' in text
    assert "run_final_experiment.py" not in text
    assert "configs/experiments/" not in text
    assert all(
        family not in smoke.BENIGN_PROMPT.casefold()
        for family in ("axios", "onnx", "aim", "httpx", "djoser")
    )
