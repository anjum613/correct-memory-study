from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "slurm/qwen32b_qualification_task.sbatch"
RERUN_SUBMISSION = ROOT / "scripts/submit_qnm_p01_technical_rerun.py"


def test_first_task_batch_uses_frozen_two_a100_configuration() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert text.count("#SBATCH --gres=gpu:a100:2") == 1
    assert text.count("#SBATCH --partition=gpu") == 1
    assert text.count("#SBATCH --no-requeue") == 1
    assert "--tensor-parallel-size 2" in text
    assert "--max-model-len 4096" in text
    assert "--max-num-seqs 1" in text
    assert "--gpu-memory-utilization 0.90" in text
    assert "--seed 0" in text
    assert "--enforce-eager" in text


def test_first_task_batch_is_offline_fresh_and_cpu_gated() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "qnm-p01-interval-merge" in text
    assert "cpu-preflight-result.json" in text
    assert 'record.get("overall") != "PASS"' in text
    assert "HF_HUB_OFFLINE=1" in text
    assert "TRANSFORMERS_OFFLINE=1" in text
    assert "--agent-timeout 600" in text
    assert "--server-pid" in text
    assert "run_qualification_task.py" in text
    assert "TECHNICAL_RERUN_OF=25908" in text
    assert "TECHNICAL_RERUN_NUMBER=1" in text
    assert "tasks/smoke_test" not in text
    assert "qwen32b-calculator-diagnostic" not in text


def test_first_task_batch_uses_bounded_runtime_and_complete_manifests() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"' in text
    assert 'RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"' in text
    assert 'export TMPDIR="$RUNTIME_SCRATCH"' in text
    assert 'export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"' in text
    assert "qualification_runtime_path.py\" validate" in text
    assert "qualification_runtime_path.py\" prepare" in text
    assert "qualification_runtime_path.py\" cleanup" in text
    assert "qualification_job_manifest.py" in text
    assert "runtime-scratch-cleanup.json" in text
    assert 'RUNTIME_SCRATCH="$ARTIFACT_DIR/runtime-scratch"' not in text


def test_submission_is_limited_to_the_one_job_25908_technical_rerun() -> None:
    text = RERUN_SUBMISSION.read_text(encoding="utf-8")

    assert 'TASK_ID = "qnm-p01-interval-merge"' in text
    assert 'TECHNICAL_RERUN_OF = "25908"' in text
    assert "TECHNICAL_RERUN_NUMBER = 1" in text
    assert "submit_with_controller_attestation" in text
    assert '"qwen32b-qnm-p01-r1"' in text
    assert "qnm-p02" not in text
    assert "qnm-p03" not in text
    assert "qnm-p04" not in text
    assert "qnm-p05" not in text
