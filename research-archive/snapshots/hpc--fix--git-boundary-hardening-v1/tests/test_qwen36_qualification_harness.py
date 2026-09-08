from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from cmpilot.qwen36_candidate import MODEL_ID, MODEL_REVISION, MODEL_SNAPSHOT, sha256_file
from cmpilot.qwen36_qualification import (
    AGENT_CONFIG,
    ALL_TASKS,
    INFRASTRUCTURE_AMENDMENT,
    QUALIFICATION_FREEZE,
    Qwen36QualificationError,
    SEED_SCHEDULE,
    SUITE_REFERENCE,
    validate_freeze_manifest,
)
from cmpilot.qwen36_submission_gate import validate_submission_gate
from cmpilot.qualification import QualificationError
from cmpilot.qualification_runner import AdapterConfig, QualificationRunConfig
from cmpilot.qualification_runner_preflight import run_qualification_runner_preflight
from scripts.generate_qwen36_qualification_batches import render
from scripts.qwen36_server_lifecycle import (
    record_exit_status,
    shutdown_process_group,
)


ROOT = Path(__file__).parents[1]
P01_SEED = 1602021252
FROZEN_HASHES = {
    "freeze": "7c8e22bcdd6d2e264ed205310b584df3643e5499e01e354b71779fc3fdcfca91",
    "seeds": "32849f701145306bff8f235747588726735125bf65beb5b37406a400803ab108",
    "suite": "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf",
}


def _base_run_config(tmp_path: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "project_root": ROOT,
        "suite_manifest": ROOT / "qualification/qwen32b-v1/suite-manifest.json",
        "task_manifest": ROOT
        / "qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json",
        "freeze_manifest": ROOT / QUALIFICATION_FREEZE,
        "artifact_directory": tmp_path / "runner-artifact",
        "base_url": "http://127.0.0.1:9/v1",
        "model": MODEL_ID,
        "mini_python": sys.executable,
        "tokenizer_path": str(MODEL_SNAPSHOT),
        "seed": P01_SEED,
        "suite_reference": ROOT / SUITE_REFERENCE,
    }
    values.update(overrides)
    return values


def test_job_25963_incomplete_config_fails_at_construction(tmp_path: Path) -> None:
    with pytest.raises(
        QualificationError,
        match="agent_config_source is required; no default is permitted",
    ):
        QualificationRunConfig(**_base_run_config(tmp_path))


def test_adapter_config_requires_an_existing_explicit_source(tmp_path: Path) -> None:
    with pytest.raises(QualificationError, match="is not a regular file"):
        AdapterConfig(
            model=MODEL_ID,
            tokenizer_path=str(MODEL_SNAPSHOT),
            base_url="http://127.0.0.1:9/v1",
            agent_config_source=tmp_path / "missing.json",
        )


def test_canonical_agent_config_is_explicit_and_old_freeze_rejects_hardening() -> None:
    assert sha256_file(ROOT / AGENT_CONFIG) == (
        "efa280b845f78242eb82e2717967160e32b3ee6f053ee2a4f17e6f38cf672a77"
    )
    with pytest.raises(
        Qwen36QualificationError,
        match="invalid successor infrastructure amendment|qualification freeze mismatch",
    ):
        validate_freeze_manifest(
            ROOT,
            ROOT / QUALIFICATION_FREEZE,
            infrastructure_amendment=ROOT / INFRASTRUCTURE_AMENDMENT,
        )


def test_historical_qualification_runner_fails_closed_before_model_boundary(
    tmp_path: Path,
) -> None:
    mini_python = Path(
        "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
    )
    if not mini_python.is_file() or not MODEL_SNAPSHOT.is_dir():
        pytest.skip("frozen HPC qualification environments are unavailable")
    with pytest.raises(
        Qwen36QualificationError,
        match="invalid successor infrastructure amendment|qualification freeze mismatch",
    ):
        run_qualification_runner_preflight(ROOT, tmp_path / "actual-runner")


def _start_server(*, ignore_term: bool) -> subprocess.Popen[str]:
    setup = (
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_term else ""
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,time; "
            + setup
            + "print('READY', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "READY"
    return process


@pytest.mark.parametrize("runner_exit", (0, 1))
def test_server_shutdown_is_independent_of_runner_exit(
    tmp_path: Path,
    runner_exit: int,
) -> None:
    process = _start_server(ignore_term=False)
    runner_file = tmp_path / f"runner-{runner_exit}.exit"
    runner_file.write_text(f"{runner_exit}\n", encoding="ascii")
    try:
        result = shutdown_process_group(
            process.pid,
            record=tmp_path / f"shutdown-{runner_exit}.json",
            term_timeout_seconds=1,
            kill_timeout_seconds=1,
            poll_interval_seconds=0.02,
        )
        process.wait(timeout=2)
        evidence = record_exit_status(
            runner_exit_file=runner_file,
            server_shutdown_exit=0,
            port_release_exit=0,
            scratch_cleanup_exit=0,
            gpu_final_exit=0,
            manifest_exit=0,
            batch_exit=runner_exit,
            record=tmp_path / f"status-{runner_exit}.json",
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)

    assert result["pass"] is True
    assert result["process_running_after"] is False
    assert evidence["qualification_runner_exit_code"] == runner_exit
    assert evidence["outer_finalizer_pass"] is True
    assert evidence["batch_exit_code"] == runner_exit


def test_stubborn_server_uses_bounded_sigkill_escalation(tmp_path: Path) -> None:
    process = _start_server(ignore_term=True)
    started = time.monotonic()
    try:
        result = shutdown_process_group(
            process.pid,
            record=tmp_path / "stubborn-shutdown.json",
            term_timeout_seconds=0.15,
            kill_timeout_seconds=1,
            poll_interval_seconds=0.02,
        )
        process.wait(timeout=2)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)

    assert time.monotonic() - started < 2
    assert result["pass"] is True
    assert result["graceful"] is False
    assert result["force_kill_used"] is True
    assert result["signals_sent"] == ["SIGTERM", "SIGKILL"]


def test_shutdown_is_idempotent_after_process_exit(tmp_path: Path) -> None:
    process = _start_server(ignore_term=False)
    first = shutdown_process_group(
        process.pid,
        record=tmp_path / "first.json",
        term_timeout_seconds=1,
        kill_timeout_seconds=1,
        poll_interval_seconds=0.02,
    )
    process.wait(timeout=2)
    second = shutdown_process_group(
        process.pid,
        record=tmp_path / "second.json",
        term_timeout_seconds=0,
        kill_timeout_seconds=0,
        poll_interval_seconds=0.02,
    )
    assert first["pass"] is True
    assert second["pass"] is True
    assert second["already_exited"] is True


def test_runner_exception_status_remains_distinct_from_outer_finalizer(
    tmp_path: Path,
) -> None:
    result = record_exit_status(
        runner_exit_file=tmp_path / "missing-runner.exit",
        server_shutdown_exit=0,
        port_release_exit=0,
        scratch_cleanup_exit=0,
        gpu_final_exit=0,
        manifest_exit=0,
        batch_exit=1,
        record=tmp_path / "status.json",
    )
    assert result["qualification_runner_exit_code"] is None
    assert result["runner_success"] is None
    assert result["outer_finalizer_pass"] is True
    assert result["batch_exit_code"] == 1


def test_all_batches_shutdown_before_testing_runner_status() -> None:
    freeze = sha256_file(ROOT / QUALIFICATION_FREEZE)
    gate = validate_submission_gate(ROOT)
    seeds = json.loads((ROOT / SEED_SCHEDULE).read_text(encoding="utf-8"))["seeds"]
    for task_id in ALL_TASKS:
        text = render(
            task_id,
            seeds[task_id],
            freeze,
            submission_gate=gate,
        )
        shutdown = text.index("cleanup_server\nserver_shutdown_status=$?")
        runner_test = text.index(
            'if [ "$runner_status" -ne 0 ]; then exit "$runner_status"; fi'
        )
        assert shutdown < runner_test
        assert 'wait "$SERVER_PID" 2>/dev/null || true' in text
        assert "qwen36_server_lifecycle.py" in text
        assert "outer-finalizer-result.json" in text
        assert "memory treatment" not in text.casefold()


def test_frozen_scientific_identities_remain_byte_exact() -> None:
    assert MODEL_REVISION == "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
    assert sha256_file(ROOT / QUALIFICATION_FREEZE) == FROZEN_HASHES["freeze"]
    assert sha256_file(ROOT / SEED_SCHEDULE) == FROZEN_HASHES["seeds"]
    assert sha256_file(ROOT / SUITE_REFERENCE) == FROZEN_HASHES["suite"]
    seeds = json.loads((ROOT / SEED_SCHEDULE).read_text(encoding="utf-8"))["seeds"]
    assert seeds["qnm-p01-interval-merge"] == P01_SEED
    assert set(seeds) == set(ALL_TASKS)
