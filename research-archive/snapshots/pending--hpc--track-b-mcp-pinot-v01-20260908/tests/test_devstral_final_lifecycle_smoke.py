from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts import run_devstral_final_lifecycle_smoke as smoke


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [{"message": {"content": "Hello."}}],
                "model": smoke.DEVSTRAL_PRODUCTION_PROFILE.served_model_name,
            }
        ).encode("utf-8")


def test_benign_request_is_single_bounded_non_scientific_probe(monkeypatch) -> None:
    observed: list[tuple[str, int]] = []

    def fake_urlopen(request, timeout):
        observed.append((request.full_url, timeout))
        return _Response()

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)

    result = smoke.benign_model_request("http://127.0.0.1:47990/v1")

    assert result["pass"] is True
    assert result["status_code"] == 200
    assert result["nonempty_content"] is True
    assert "content" not in result
    assert observed == [
        (
            "http://127.0.0.1:47990/v1/chat/completions",
            smoke.BENIGN_REQUEST_TIMEOUT_SECONDS,
        )
    ]


def test_smoke_uses_final_service_lifecycle_without_family_or_task(
    tmp_path: Path, monkeypatch
) -> None:
    observed: dict[str, object] = {}

    class FakeService:
        def __init__(self, *, profile, project_root):
            observed["profile"] = profile
            observed["project_root"] = project_root

        def start(self, *, attempt_directory, run_id, slurm_job_id):
            observed["attempt"] = attempt_directory
            observed["run_id"] = run_id
            observed["job_id"] = slurm_job_id
            for name, value in (
                ("gpu-allocation.json", {"pass": True}),
                ("runtime-integrity.json", {"pass": True}),
                ("server-startup.json", {"pass": True}),
                ("server-health.json", {"pass": True, "status_code": 200}),
                ("server-models.json", {"pass": True}),
            ):
                (attempt_directory / name).write_text(json.dumps(value))
            (attempt_directory / "server.pid").write_text("123\n")
            return "http://127.0.0.1:47990/v1"

        def shutdown(self):
            observed["shutdown"] = True
            return {"complete": True, "pass": True}

    preflight = {
        "checks": {
            "scientific_family_absent": True,
            "target_task_absent": True,
        },
        "pass": True,
        "scientific_evidence": False,
    }
    monkeypatch.setattr(smoke, "build_preflight", lambda: preflight)
    monkeypatch.setattr(smoke, "DevstralModelService", FakeService)
    monkeypatch.setattr(
        smoke,
        "benign_model_request",
        lambda _base: {"pass": True, "status_code": 200},
    )

    result = smoke.run_smoke(artifact_root=tmp_path, slurm_job_id="30123")

    assert result["pass"] is True
    assert result["scientific_evidence"] is False
    assert all(result["checks"].values())
    assert observed["profile"] is smoke.DEVSTRAL_PRODUCTION_PROFILE
    assert observed["run_id"] == "technical-smoke-30123"
    assert observed["shutdown"] is True
    attempt = Path(result["attempt_directory"])
    assert attempt.name == f"slurm-30123-{smoke.SMOKE_ID}"
    assert json.loads((attempt / "smoke-preflight.json").read_text()) == preflight


def test_batch_is_bounded_non_scientific_and_invokes_smoke_once() -> None:
    batch = smoke.BATCH_PATH
    source = batch.read_text(encoding="utf-8")
    syntax = subprocess.run(
        ("bash", "-n", str(batch)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert syntax.returncode == 0, syntax.stderr
    assert "#SBATCH --gres=gpu:a100:2" in source
    assert "#SBATCH --time=01:00:00" in source
    assert "#SBATCH --no-requeue" in source
    assert source.count("run_devstral_final_lifecycle_smoke.py") == 2
    assert "sbatch" not in source
    for prohibited_family in ("axios", "onnx", "aim", "httpx", "djoser"):
        assert prohibited_family not in source.lower()
