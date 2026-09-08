from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from cmpilot.qwen36_candidate import sha256_file
from cmpilot.qwen36_qualification import (
    ALL_TASKS,
    QUALIFICATION_FREEZE,
    SEED_SCHEDULE,
    validate_seed_schedule,
)
from cmpilot.qwen36_submission_gate import (
    SUBMISSION_GATE,
    batch_gate_equivalence,
    validate_submission_gate,
)
from scripts.generate_qwen36_qualification_batches import render


ROOT = Path(__file__).parents[1]
STALE_GATE = (
    "/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/"
    "cpu-preflight-qualification-harness-fix-25963/cpu-preflight-result.json"
)
P01 = "qnm-p01-interval-merge"
P01_SEED = 1602021252


def _active_batches() -> list[Path]:
    paths = [
        ROOT / "slurm" / f"qwen36_{task_id.replace('-', '_')}.sbatch"
        for task_id in ALL_TASKS
    ]
    paths.append(
        ROOT
        / "slurm/qwen36_qnm_p01_interval_merge_technical_rerun_26036_1.sbatch"
    )
    return paths


def test_canonical_submission_gate_is_complete_and_byte_validated() -> None:
    gate = validate_submission_gate(ROOT)

    assert gate["pass"] is True
    assert all(gate["checks"].values())
    assert gate["record_path"] == (ROOT / SUBMISSION_GATE).resolve()
    assert gate["record_sha256"] == sha256_file(ROOT / SUBMISSION_GATE)
    assert gate["scientific_freeze_sha256"] == (
        "7c8e22bcdd6d2e264ed205310b584df3643e5499e01e354b71779fc3fdcfca91"
    )
    assert gate["seed_schedule_sha256"] == (
        "32849f701145306bff8f235747588726735125bf65beb5b37406a400803ab108"
    )
    assert gate["suite_reference_sha256"] == (
        "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf"
    )


def test_generator_and_submitter_import_the_same_gate_validator() -> None:
    generator = (ROOT / "scripts/generate_qwen36_qualification_batches.py").read_text()
    submitter = (ROOT / "scripts/submit_qwen36_qualification.py").read_text()

    assert "validate_submission_gate" in generator
    assert "validate_submission_gate" in submitter
    assert "CPU_GATE = (" not in generator
    assert "CPU_GATE = QWEN36_ARTIFACT_ROOT" not in submitter
    assert "cpu-preflight-qualification-harness-fix-25963-ready" not in generator
    assert "cpu-preflight-qualification-harness-fix-25963-ready" not in submitter


def test_cpu_gate_records_the_frozen_seed_schedule_digest_explicitly() -> None:
    source = (ROOT / "scripts/qwen36_qualification_cpu_gate.py").read_text()

    assert 'result["seed_schedule_sha256"] = seed_schedule_sha256' in source
    assert 'submission_gate["seed_schedule_sha256"]' in source


def test_one_gate_value_updates_render_and_equivalence_together() -> None:
    gate = validate_submission_gate(ROOT)
    changed = deepcopy(gate)
    changed["cpu_gate_result_path"] = Path("/shared/example/new-gate.json")
    changed["cpu_gate_result_sha256"] = "f" * 64

    text = render(P01, P01_SEED, submission_gate=changed)
    checks = batch_gate_equivalence(
        text,
        gate=changed,
        task_id=P01,
        seed=P01_SEED,
    )

    assert "CPU_GATE=/shared/example/new-gate.json" in text
    assert f"EXPECTED_CPU_GATE_SHA256={'f' * 64}" in text
    assert all(checks.values())


def test_stale_gate_path_is_rejected_before_submission() -> None:
    gate = validate_submission_gate(ROOT)
    text = render(P01, P01_SEED, submission_gate=gate)
    stale = text.replace(str(gate["cpu_gate_result_path"]), STALE_GATE)

    checks = batch_gate_equivalence(
        stale,
        gate=gate,
        task_id=P01,
        seed=P01_SEED,
    )

    assert checks["cpu_gate"] is False
    assert not all(checks.values())


def test_wrong_amendment_freeze_and_seed_are_each_rejected() -> None:
    gate = validate_submission_gate(ROOT)
    text = render(P01, P01_SEED, submission_gate=gate)
    mutations = (
        text.replace(
            f"EXPECTED_AMENDMENT_SHA256={gate['infrastructure_amendment_sha256']}",
            f"EXPECTED_AMENDMENT_SHA256={'a' * 64}",
            1,
        ),
        text.replace(
            f"EXPECTED_FREEZE_SHA256={gate['scientific_freeze_sha256']}",
            f"EXPECTED_FREEZE_SHA256={'b' * 64}",
            1,
        ),
        text.replace("TASK_SEED=1602021252", "TASK_SEED=1602021253", 1),
    )

    for mutated in mutations:
        checks = batch_gate_equivalence(
            mutated,
            gate=gate,
            task_id=P01,
            seed=P01_SEED,
        )
        assert not all(checks.values())


def test_all_active_batches_share_one_gate_and_all_frozen_seeds() -> None:
    gate = validate_submission_gate(ROOT)
    seeds = validate_seed_schedule(ROOT / SEED_SCHEDULE)["seeds"]
    record_assignment = f"SUBMISSION_GATE_RECORD=$PROJECT/{SUBMISSION_GATE.as_posix()}"
    digest_assignment = f"EXPECTED_SUBMISSION_GATE_SHA256={gate['record_sha256']}"

    for task_id, path in zip(ALL_TASKS, _active_batches()[: len(ALL_TASKS)]):
        text = path.read_text(encoding="utf-8")
        assert record_assignment in text
        assert digest_assignment in text
        assert f"TASK_SEED={seeds[task_id]}" in text
        assert STALE_GATE not in text
        assert all(
            batch_gate_equivalence(
                text,
                gate=gate,
                task_id=task_id,
                seed=seeds[task_id],
            ).values()
        )

    rerun = _active_batches()[-1].read_text(encoding="utf-8")
    assert "TECHNICAL_RERUN_OF=26036" in rerun
    assert "TECHNICAL_RERUN_NUMBER=1" in rerun
    assert "TECHNICAL_ROOT_QUALIFICATION=25953" in rerun
    assert "QUALIFICATION_SEED=1602021252" in rerun
    assert STALE_GATE not in rerun


def test_scientific_and_runtime_policies_are_unchanged() -> None:
    gate = validate_submission_gate(ROOT)
    text = render(P01, P01_SEED, submission_gate=gate)

    assert sha256_file(ROOT / QUALIFICATION_FREEZE) == gate["scientific_freeze_sha256"]
    assert "--dtype bfloat16" in text
    assert "--tensor-parallel-size 2" in text
    assert "--max-model-len 32768" in text
    assert "--gpu-memory-utilization 0.90" in text
    assert "--reasoning-parser qwen3" in text
    assert 'RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID' in text
    assert "MAX_SERVER_BIND_ATTEMPTS=4" in text
    assert "--term-timeout-seconds 30" in text
    assert "--kill-timeout-seconds 10" in text
    assert '--agent-config-source "$AGENT_CONFIG_SOURCE"' in text
    assert "memory treatment" not in text.casefold()


def test_submitter_authorizes_only_the_job_26036_p01_rerun() -> None:
    text = (ROOT / "scripts/submit_qwen36_qualification.py").read_text(
        encoding="utf-8"
    )

    assert 'TECHNICAL_RERUN_TASK = "qnm-p01-interval-merge"' in text
    assert 'TECHNICAL_RERUN_OF = "26036"' in text
    assert "TECHNICAL_RERUN_NUMBER = 1" in text
    assert "only technical rerun 1 of job 26036 is authorized" in text
