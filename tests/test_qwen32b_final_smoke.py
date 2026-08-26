from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.integrations.miniswe.command_authorization import POLICY_VERSION
from cmpilot.qwen32b_final_smoke import (
    ARTIFACT_ROOT,
    FROZEN_TAG_TARGET,
    PORT,
    SMOKE_ID,
    TASK_ID,
    build_preflight,
    validate_batch_contract,
    validate_completion,
    validate_runtime_integrity,
    write_preflight,
)
from cmpilot.server_command import load_command_argv
from scripts import submit_qwen32b_final_smoke as submitter


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm" / "qwen32b_final_smoke.sbatch"


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def test_preflight_freezes_prior_fixture_and_exact_qwen_profile() -> None:
    record = build_preflight(ROOT)

    assert record["pass"] is True
    assert record["confirmatory"] is False
    assert record["scientific_evidence"] is False
    assert record["smoke_id"] == SMOKE_ID
    assert record["fixture"]["task_id"] == TASK_ID
    assert record["fixture"]["prior_use"]["job_id"] == "25913"
    assert record["fixture"]["prior_use"]["prior_action_executed_count"] >= 1
    assert record["frozen_harness_commit"] == FROZEN_TAG_TARGET
    assert record["model_profile_sha256"] == QWEN32B_PROFILE.identity_sha256()
    assert tuple(record["server_argv"]) == QWEN32B_PROFILE.server_argv(port=PORT)
    assert record["resources"] == {
        "cpus": 8,
        "dtype": "bfloat16",
        "gpus": 2,
        "gpu_type": "a100",
        "host_memory": "128G",
        "max_model_length": 4096,
        "nodes": 1,
        "tensor_parallel_size": 2,
        "walltime": "00:30:00",
    }


def test_preflight_writes_canonical_command_once(tmp_path: Path) -> None:
    output = tmp_path / "preflight"

    write_preflight(ROOT, output)

    assert load_command_argv(output / "server-command.json") == (
        QWEN32B_PROFILE.server_argv(port=PORT)
    )
    with pytest.raises(FileExistsError):
        write_preflight(ROOT, output)


def test_batch_is_thin_bounded_and_does_not_copy_server_argv() -> None:
    checks = validate_batch_contract(ROOT)
    text = BATCH.read_text(encoding="utf-8")

    assert all(checks.values()), checks
    assert "vllm.entrypoints.openai.api_server" not in text
    assert 'setsid "${SERVER_COMMAND[@]}"' in text
    assert "--agent-config-source \"$AGENT_CONFIG\"" in text
    assert "--server-pid \"$SERVER_PID\"" in text
    assert "--runtime-integrity \"$ARTIFACT_DIR/runtime-integrity.json\"" in text
    assert "technical-smoke-result.json" in text
    assert "mkdir \"$ARTIFACT_DIR\"" in text
    assert "mkdir -p \"$ARTIFACT_DIR\"" not in text
    assert str(ARTIFACT_ROOT / "jobs") in text
    assert "/run-artifacts/" not in str(ARTIFACT_ROOT)


def test_runtime_integrity_requires_exact_qwen_environment(tmp_path: Path) -> None:
    fingerprint = tmp_path / "fingerprint.json"
    content = tmp_path / "content.json"
    environment = QWEN32B_PROFILE.environment
    _json(
        fingerprint,
        {
            "canonical_inventory_sha256": environment.environment_fingerprint,
            "interpreter": str(environment.server_python),
            "schema": "environment-fingerprint-v2",
        },
    )
    _json(
        content,
        {
            "authoritative": True,
            "canonical_inventory_sha256": environment.environment_content_digest,
            "schema": "environment-content-digest-v1",
        },
    )

    assert validate_runtime_integrity(fingerprint, content)["pass"] is True
    changed = json.loads(content.read_text())
    changed["canonical_inventory_sha256"] = "0" * 64
    _json(content, changed)
    assert validate_runtime_integrity(fingerprint, content)["pass"] is False


def test_completion_requires_action_parser_finalizer_and_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    _json(
        run / "result.json",
        {
            "model_revision": QWEN32B_PROFILE.model_revision,
            "task_id": TASK_ID,
            "treatment": "no_memory",
        },
    )
    _json(
        run / "trajectory-metrics.json",
        {
            "command_count": 1,
            "executed_action_count": 1,
            "model_request_count": 1,
            "policy_version": POLICY_VERSION,
            "technical_validity": "PASS",
        },
    )
    _json(run / "shutdown.json", {"pass": True})
    runtime = tmp_path / "runtime.json"
    cleanup = tmp_path / "cleanup.json"
    models = tmp_path / "models.json"
    health = tmp_path / "health.txt"
    _json(runtime, {"pass": True})
    _json(cleanup, {"pass": True})
    _json(models, {"data": [{"id": QWEN32B_PROFILE.served_model_name}]})
    health.write_text("200\n", encoding="ascii")
    monkeypatch.setattr(
        "cmpilot.qwen32b_final_smoke.validate_total_finalization_artifacts",
        lambda artifact: {"pass": artifact == run},
    )

    record = validate_completion(
        run,
        health_status_path=health,
        models_response_path=models,
        runtime_integrity_path=runtime,
        server_cleanup_path=cleanup,
        runner_exit_code=0,
    )

    assert record["pass"] is True
    assert record["scientific_evidence"] is False
    assert record["confirmatory"] is False
    assert all(record["checks"].values())


def test_submitter_submits_once_through_controller_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_root = tmp_path / "artifacts"
    evidence = tmp_path / "submission"
    calls: list[tuple[Path, Path, str]] = []

    def fake_command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ("status", "--porcelain"):
            stdout = ""
        elif argv[-2:] == ("rev-parse", "HEAD"):
            stdout = "f" * 40 + "\n"
        elif "rev-list" in argv:
            stdout = FROZEN_TAG_TARGET + "\n"
        elif argv[0].endswith("squeue"):
            stdout = ""
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def fake_submit(
        batch: Path, *, evidence_dir: Path, begin: str
    ) -> dict[str, object]:
        calls.append((batch, evidence_dir, begin))
        return {
            "attestation": {"controller_digest": "a" * 64},
            "job_id": "27123",
            "pass": True,
        }

    monkeypatch.setattr(submitter, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(submitter, "command", fake_command)
    monkeypatch.setattr(submitter, "submit_with_controller_attestation", fake_submit)

    status = submitter.main(
        (
            "--script",
            str(BATCH),
            "--evidence-directory",
            str(evidence),
            "--begin",
            "now+1minute",
        )
    )

    assert status == 0
    assert calls == [(BATCH.resolve(), evidence, "now+1minute")]
    record = json.loads((evidence / "submission-record.json").read_text())
    assert record["slurm_job_id"] == "27123"
    assert record["submission_once"] is True
    assert record["confirmatory"] is False
    assert record["scientific_evidence"] is False


def test_submitter_has_no_direct_sbatch_path() -> None:
    text = (ROOT / "scripts" / "submit_qwen32b_final_smoke.py").read_text(
        encoding="utf-8"
    )

    assert text.count("submit_with_controller_attestation(") == 1
    assert '"sbatch"' not in text
    assert "project worktree must be clean before GPU submission" in text
    assert "already has immutable job artifacts" in text
