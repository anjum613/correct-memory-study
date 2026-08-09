from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "slurm/qwen32b_qualification_task.sbatch"


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
    assert "tasks/smoke_test" not in text
    assert "qwen32b-calculator-diagnostic" not in text


def test_first_task_batch_uses_shared_scratch_and_complete_manifests() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'RUNTIME_SCRATCH="$ARTIFACT_DIR/runtime-scratch"' in text
    assert 'export TMPDIR="$RUNTIME_SCRATCH"' in text
    assert "qualification_job_manifest.py" in text
    assert "runtime-scratch-cleanup.json" in text
    assert "/tmp/" not in text
