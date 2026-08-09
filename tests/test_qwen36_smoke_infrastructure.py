from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from cmpilot.qwen36_candidate import ENVIRONMENT_PATH, MODEL_REVISION


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm/qwen36_model_load_request_smoke.sbatch"


def test_batch_requests_exactly_two_a100s_and_conservative_host_resources() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert text.splitlines().count("#SBATCH --gres=gpu:a100:2") == 1
    assert text.splitlines().count("#SBATCH --cpus-per-task=16") == 1
    assert text.splitlines().count("#SBATCH --mem=192G") == 1
    assert text.splitlines().count("#SBATCH --nodes=1") == 1
    assert text.splitlines().count("#SBATCH --no-requeue") == 1


def test_batch_uses_only_pinned_bf16_tp2_32k_model_serving() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert f"MODEL_REVISION={MODEL_REVISION}" in text
    assert "--dtype bfloat16" in text
    assert text.count("--tensor-parallel-size 2") == 2
    assert text.count("--max-model-len 32768") == 2
    assert text.count("--max-num-seqs 1") == 2
    assert text.count("--gpu-memory-utilization 0.90") == 2
    assert text.count("--language-model-only") == 2
    assert "--quantization" not in text
    assert "--trust-remote-code" not in text


def test_smoke_is_offline_fresh_and_does_not_consume_a_qualification_task() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert "HF_HUB_OFFLINE=1" in text
    assert "TRANSFORMERS_OFFLINE=1" in text
    assert 'ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"' in text
    assert 'RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"' in text
    assert "run_qualification_task.py" not in text
    assert "qnm-p01" not in text
    assert "reference-patches" not in text
    assert "memory-treatment" not in text


def test_batch_runs_one_project_transport_request_and_preserves_cleanup() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    client = (ROOT / "scripts/qwen36_smoke_client.py").read_text(encoding="utf-8")

    assert batch.count("scripts/qwen36_smoke_client.py") == 1
    assert client.count("transport.complete(") == 1
    assert "completed_model_requests" in client
    assert "cleanup_server" in batch
    assert "cleanup_scratch" in batch
    assert "finalize_qwen36_smoke.py" in batch
    assert "gpu-memory-after-shutdown.csv" in batch


def test_batch_uses_separate_immutable_environment_and_short_ipc_path() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert str(ENVIRONMENT_PATH / "bin/python") in text
    assert "/home/s224049759/environments/vllm-smoke/bin/python" not in text
    assert 'VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"' in text
    assert 'TMPDIR="$RUNTIME_SCRATCH"' in text
    assert "runtime-ipc-path-budget.json" in text
    assert "runtime-scratch-cleanup.json" in text


def test_batch_and_shell_scripts_have_valid_bash_syntax() -> None:
    paths = [BATCH, *sorted((ROOT / "scripts").glob("*.sh"))]
    completed = subprocess.run(
        ("/usr/bin/bash", "-n", *map(str, paths)),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_submission_checks_queue_once_and_uses_controller_attestation() -> None:
    source = (ROOT / "scripts/submit_qwen36_smoke.py").read_text(encoding="utf-8")

    assert 'JOB_NAME = "qwen36-load-smoke-v1"' in source
    assert source.count('"/slurm/bin/squeue"') == 1
    assert source.count("submit_with_controller_attestation(") == 1
    assert "worktree must be clean" in source
    assert "candidate manifest changed after CPU preflight" in source


def test_new_python_sources_compile() -> None:
    paths = [
        ROOT / "src/cmpilot/qwen36_candidate.py",
        ROOT / "scripts/capture_qwen36_environment.py",
        ROOT / "scripts/create_qwen36_candidate_manifest.py",
        ROOT / "scripts/finalize_qwen36_smoke.py",
        ROOT / "scripts/qwen36_compatibility_probe.py",
        ROOT / "scripts/qwen36_cpu_preflight.py",
        ROOT / "scripts/qwen36_gpu_probe.py",
        ROOT / "scripts/qwen36_smoke_client.py",
        ROOT / "scripts/stage_qwen36_snapshot.py",
        ROOT / "scripts/submit_qwen36_smoke.py",
        ROOT / "scripts/verify_qwen36_environment.py",
    ]
    completed = subprocess.run(
        (sys.executable, "-m", "py_compile", *map(str, paths)),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_environment_verifier_imports_when_invoked_by_absolute_path() -> None:
    verifier = ROOT / "scripts/verify_qwen36_environment.py"
    completed = subprocess.run(
        (str(ENVIRONMENT_PATH / "bin/python"), str(verifier), "--help"),
        cwd=Path("/"),
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONNOUSERSITE": "1"},
    )

    assert completed.returncode == 0, completed.stderr
    assert "Compare the live Qwen3.6 environment" in completed.stdout


def test_corrected_cpu_gate_uses_a_new_preservation_path() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    preflight = (ROOT / "scripts/qwen36_cpu_preflight.py").read_text(encoding="utf-8")
    submission = (ROOT / "scripts/submit_qwen36_smoke.py").read_text(encoding="utf-8")

    assert 'ARTIFACT_ROOT / "cpu-preflight-v2"' in preflight
    assert "cpu-preflight-v2/cpu-preflight-result.json" in batch
    assert 'ARTIFACT_ROOT / "cpu-preflight-v2/cpu-preflight-result.json"' in submission
