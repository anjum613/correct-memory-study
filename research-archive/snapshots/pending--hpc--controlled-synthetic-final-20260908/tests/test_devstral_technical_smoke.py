from __future__ import annotations

import json
from pathlib import Path
import subprocess

from cmpilot.devstral_profile import (
    ENVIRONMENT_CONTENT_DIGEST_SHA256,
    ENVIRONMENT_FINGERPRINT_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    build_devstral_server_argv,
)
from cmpilot.devstral_serialization import PINNED_TEKKEN_SHA256
from cmpilot.devstral_technical_smoke import (
    BATCH_PATH,
    EXPECTED_SNAPSHOT_FREEZE_SHA256,
    EXPECTED_SNAPSHOT_IDENTITY_SHA256,
    authorization_probe,
    finalize_job,
    runtime_integrity_from_verifier,
    validate_batch_contract,
    validate_completion,
)
from scripts import submit_devstral_technical_smoke as submitter
from cmpilot.server_command import encode_nul_delimited


ROOT = Path(__file__).parents[1]
BATCH = ROOT / BATCH_PATH


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _verification() -> dict[str, object]:
    return {
        "checks": {"all_existing_checks": True},
        "environment_content_digest": {
            "canonical_inventory_sha256": ENVIRONMENT_CONTENT_DIGEST_SHA256
        },
        "environment_fingerprint": {
            "canonical_inventory_sha256": ENVIRONMENT_FINGERPRINT_SHA256
        },
        "production_ready": True,
        "snapshot_freeze": {
            "freeze_sha256": EXPECTED_SNAPSHOT_FREEZE_SHA256,
            "snapshot_identity_sha256": EXPECTED_SNAPSHOT_IDENTITY_SHA256,
            "status": "READY",
            "valid": True,
        },
        "status": "READY",
    }


def test_runtime_preflight_requires_ready_verifier_and_exact_batch() -> None:
    record = runtime_integrity_from_verifier(ROOT, _verification())

    assert record["pass"] is True
    assert record["scientific_evidence"] is False
    assert record["model_id"] == MODEL_ID
    assert record["model_revision"] == MODEL_REVISION
    assert record["resources"] == {
        "cpus": 8,
        "dtype": "bfloat16",
        "gpus": 2,
        "gpu_type": "a100",
        "host_memory": "128G",
        "max_model_length": 4096,
        "nodes": 1,
        "quantization": None,
        "tensor_parallel_size": 2,
        "walltime": "01:00:00",
    }
    assert all(validate_batch_contract(ROOT).values())
    assert "--load-format" in record["server_argv"]
    assert "mistral" in record["server_argv"]


def test_authorization_probe_blocks_without_executing() -> None:
    record = authorization_probe()

    assert record["pass"] is True
    assert record["allowed"]["authorized"] is True
    assert record["prohibited"]["authorized"] is False
    assert record["prohibited"]["category"] == "prohibited_network_access"


def test_completion_requires_live_serialization_functionality_and_total_finalizer(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "job"
    run = artifact / "runs/smoke-test"
    run.mkdir(parents=True)
    _write_json(
        run / "run.json",
        {
            "after_test_exit_code": 0,
            "cleanup_complete": True,
            "command_count": 1,
            "executed_action_count": 1,
            "external_oracle_result": "pass",
            "model_protocol_technical_validity": "PASS",
            "model_request_count": 1,
            "policy_version": "calculator-capability-policy-v3",
            "prohibited_command_executed": False,
            "task_name": "smoke_test",
            "technical_validity": "pass",
            "termination_reason": "Submitted",
            "usage_total": 42,
        },
    )
    _write_json(
        run / "classification.json",
        {
            "classification": "secure_functional_success",
            "success_checks": {"source_template_unchanged": True},
        },
    )
    (run / "final.patch").write_text("synthetic patch\n", encoding="utf-8")
    (run / "model-transport.jsonl").write_text(
        json.dumps(
            {
                "classification": "success",
                "request_sha256": "a" * 64,
                "response_sha256": "b" * 64,
                "status_code": 200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "request-budgets.jsonl").write_text(
        json.dumps(
            {
                "tokenizer": {
                    "response_conversion": None,
                    "schema": "devstral-mistral-chat-tokenizer-identity-v1",
                    "tekken_sha256": PINNED_TEKKEN_SHA256,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        artifact / "runtime-integrity.json",
        {"model_revision": MODEL_REVISION, "pass": True},
    )
    _write_json(artifact / "authorization-probe.json", authorization_probe())
    _write_json(artifact / "server-cleanup.json", {"pass": True})
    _write_json(artifact / "models-response.json", {"data": [{"id": MODEL_ID}]})
    (artifact / "health-http-status.txt").write_text("200\n", encoding="ascii")
    (artifact / "gpu-memory-samples.csv").write_text(
        "0, NVIDIA A100-PCIE-40GB, 35000\n"
        "1, NVIDIA A100-PCIE-40GB, 35100\n",
        encoding="utf-8",
    )

    final = finalize_job(artifact, runner_exit_code=0)
    result = validate_completion(artifact, runner_exit_code=0)

    assert final["scientific_evidence"] is False
    assert result["pass"] is True
    assert all(result["checks"].values())
    assert result["peak_gpu_memory_mib"] == {"0": 35000, "1": 35100}


def test_submitter_requires_clean_ready_state_and_attests_once(
    tmp_path: Path, monkeypatch
) -> None:
    artifact_root = tmp_path / "artifacts"
    evidence = artifact_root / "submissions/primary"
    calls: list[tuple[Path, Path, str]] = []

    def fake_command(
        argv: tuple[str, ...], *, timeout: int = 60
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        if argv[-2:] == ("status", "--porcelain"):
            stdout = ""
        elif argv[-2:] == ("rev-parse", "HEAD"):
            stdout = "f" * 40 + "\n"
        elif argv[0].endswith("squeue"):
            stdout = ""
        elif argv[0] == str(submitter.SERVER_PYTHON):
            stdout = json.dumps(_verification())
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def fake_submit(
        batch: Path, *, evidence_dir: Path, begin: str
    ) -> dict[str, object]:
        evidence_dir.mkdir(parents=True)
        calls.append((batch, evidence_dir, begin))
        return {
            "attestation": {"controller_digest": "c" * 64},
            "job_id": "30123",
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
        )
    )

    assert status == 0
    assert calls == [(BATCH.resolve(), evidence, "now+1minute")]
    record = json.loads((evidence / "submission-record.json").read_text())
    assert record["slurm_job_id"] == "30123"
    assert record["scientific_evidence"] is False
    assert record["requested_resources"]["gpus"] == 2


def test_batch_has_valid_bash_syntax_and_submitter_has_no_direct_sbatch() -> None:
    completed = subprocess.run(
        ("bash", "-n", str(BATCH)), check=False, capture_output=True, text=True
    )
    submit = (ROOT / "scripts/submit_devstral_technical_smoke.py").read_text()

    assert completed.returncode == 0, completed.stderr
    assert '"sbatch"' not in submit
    assert submit.count("submit_with_controller_attestation(") == 1


def test_devstral_command_extractor_is_lossless_and_fail_closed(
    tmp_path: Path,
) -> None:
    command = build_devstral_server_argv(port=49827)
    source = tmp_path / "server-command.json"
    source.write_text(json.dumps(list(command)) + "\n", encoding="utf-8")
    result = tmp_path / "result.json"
    extractor = ROOT / "scripts/extract_devstral_server_command.py"

    completed = subprocess.run(
        (
            "/home/s224049759/environments/cmpilot-conda/bin/python",
            str(extractor),
            "--command-json",
            str(source),
            "--result",
            str(result),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == encode_nul_delimited(command)
    assert json.loads(result.read_text())["label"] == (
        "DEVSTRAL_SERVER_COMMAND_EXTRACTION_PASS"
    )

    mutated = list(command)
    mutated.extend(("--quantization", "awq"))
    source.write_text(json.dumps(mutated) + "\n", encoding="utf-8")
    rejected = subprocess.run(
        (
            "/home/s224049759/environments/cmpilot-conda/bin/python",
            str(extractor),
            "--command-json",
            str(source),
            "--result",
            str(tmp_path / "rejected.json"),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=20,
    )

    assert rejected.returncode == 79
    assert rejected.stdout == b""
