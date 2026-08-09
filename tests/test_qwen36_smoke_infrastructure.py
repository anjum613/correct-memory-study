from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from cmpilot.qwen36_candidate import ENVIRONMENT_PATH, MODEL_REVISION


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm/qwen36_model_load_request_smoke.sbatch"
TECHNICAL_INVALID = (
    ROOT / "qualification/qwen36-v1/technical-invalid-smoke-25933.json"
)
TECHNICAL_INVALID_25938 = (
    ROOT / "qualification/qwen36-v1/technical-invalid-smoke-25938.json"
)


def test_batch_requests_exactly_two_a100s_and_conservative_host_resources() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert text.splitlines().count("#SBATCH --gres=gpu:a100:2") == 1
    assert text.splitlines().count("#SBATCH --cpus-per-task=16") == 1
    assert text.splitlines().count("#SBATCH --mem=192G") == 1
    assert text.splitlines().count("#SBATCH --nodes=1") == 1
    assert text.splitlines().count("#SBATCH --no-requeue") == 1


def test_job_25933_is_preserved_as_unscored_technical_invalid_evidence() -> None:
    import json

    record = json.loads(TECHNICAL_INVALID.read_text(encoding="utf-8"))

    assert record["job"]["slurm_job_id"] == "25933"
    assert record["technical_validity"] == "FAIL"
    assert record["technical_failure_class"] == "PRE_SERVER_GPU_DIAGNOSTIC_FAILURE"
    assert (
        record["technical_failure_detail"]
        == "UNSUPPORTED_NVIDIA_SMI_MIG_DISPLAY_QUERY"
    )
    assert record["exact_failing_command"] == "/usr/bin/nvidia-smi -q -d MIG"
    assert record["model_requests"] == 0
    assert record["model_load_attempted"] is False
    assert record["qualification_scored"] is False


def test_job_25938_is_preserved_as_unscored_technical_invalid_evidence() -> None:
    import json

    record = json.loads(TECHNICAL_INVALID_25938.read_text(encoding="utf-8"))

    assert record["job"]["slurm_job_id"] == "25938"
    assert record["technical_validity"] == "FAIL"
    assert (
        record["technical_failure_class"]
        == "PRE_HEALTHCHECK_SMOKE_CLIENT_IMPORT_FAILURE"
    )
    assert (
        record["technical_failure_detail"]
        == "WRONG_PYTHON_INTERPRETER_MISSING_PYDANTIC"
    )
    assert record["technical_parent"] == "25933"
    assert record["model_requests"] == 0
    assert record["http_requests"] == 0
    assert record["model_load_success"] is False
    assert record["qualification_scored"] is False


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


def test_mig_diagnostic_is_structured_informational_and_legacy_query_is_absent() -> None:
    text = BATCH.read_text(encoding="utf-8")

    assert "/usr/bin/nvidia-smi -q -d MIG" not in text
    assert "scripts/capture_gpu_diagnostic.py" in text
    assert "--query-gpu=index,name,pci.bus_id,mig.mode.current" in text
    assert text.count("--policy informational") == 1
    # The ordinary visibility report remains mandatory under set -e and captures MIG.
    assert '/usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"' in text
    assert 'nvidia-smi -L > "$ARTIFACT_DIR/nvidia-smi-list.txt"' in text
    assert 'nvidia-smi topo -m > "$ARTIFACT_DIR/nvidia-smi-topology.txt"' in text


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
        ROOT / "scripts/capture_gpu_diagnostic.py",
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


def test_technical_rerun_cpu_gate_uses_a_new_preservation_path() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    preflight = (ROOT / "scripts/qwen36_cpu_preflight.py").read_text(encoding="utf-8")
    submission = (ROOT / "scripts/submit_qwen36_smoke.py").read_text(encoding="utf-8")

    assert 'ARTIFACT_ROOT / "cpu-preflight-v4"' in preflight
    assert "cpu-preflight-v4/cpu-preflight-result.json" in batch
    assert 'ARTIFACT_ROOT / "cpu-preflight-v4/cpu-preflight-result.json"' in submission


def test_smoke_is_explicitly_the_only_technical_rerun_of_job_25938() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    submission = (ROOT / "scripts/submit_qwen36_smoke.py").read_text(
        encoding="utf-8"
    )

    assert "TECHNICAL_RERUN_OF=25938" in batch
    assert "TECHNICAL_RERUN_NUMBER=1" in batch
    assert "TECHNICAL_ROOT_SMOKE=25933" in batch
    assert 'TECHNICAL_RERUN_OF = "25938"' in submission
    assert "TECHNICAL_RERUN_NUMBER = 1" in submission
    assert 'TECHNICAL_ROOT_SMOKE = "25933"' in submission
    assert '"technical_rerun_of": TECHNICAL_RERUN_OF' in submission
    assert '"technical_rerun_number": TECHNICAL_RERUN_NUMBER' in submission
    assert '"technical_root_smoke": TECHNICAL_ROOT_SMOKE' in submission
