#!/usr/bin/env python3
"""Collect server evidence and build the immutable smoke-test-3 result."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cmpilot.outcome_classifier import (
    classification_dimensions,
    correct_post_server_classification,
)


MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def request(url: str, timeout: float = 5) -> dict[str, object]:
    request_object = Request(url, method="GET")
    try:
        with urlopen(request_object, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "headers": {str(key): str(value) for key, value in response.headers.items()},
                "body": body,
            }
    except HTTPError as error:
        return {
            "status_code": error.code,
            "headers": {str(key): str(value) for key, value in error.headers.items()},
            "body": error.read().decode("utf-8", errors="replace"),
        }


def capture_nvidia_smi(path: Path) -> None:
    result = subprocess.run(["nvidia-smi"], text=True, capture_output=True, check=False)
    path.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"nvidia-smi failed with exit code {result.returncode}")


def probe_server(args: argparse.Namespace) -> int:
    artifact_dir: Path = args.artifact_dir
    health_url = args.base_url.rstrip("/") + "/health"
    models_url = args.base_url.rstrip("/") + "/v1/models"
    started = time.monotonic()
    deadline = started + args.startup_timeout
    attempts = 0
    last_error = ""
    health: dict[str, object] | None = None

    while time.monotonic() < deadline:
        if not process_alive(args.server_pid):
            raise RuntimeError("vLLM exited before becoming healthy")
        attempts += 1
        try:
            health = request(health_url)
        except (URLError, TimeoutError, OSError) as error:
            last_error = repr(error)
            time.sleep(2)
            continue
        if 200 <= int(health["status_code"]) < 300:
            break
        raise RuntimeError(f"/health failed: {health['status_code']} {health['body']!r}")
    else:
        raise RuntimeError(f"vLLM startup timed out; last error: {last_error}")

    assert health is not None
    health_text = (
        f"status_code={health['status_code']}\n"
        f"headers={json.dumps(health['headers'], sort_keys=True)}\n"
        f"body={health['body']}\n"
    )
    (artifact_dir / "health-response.txt").write_text(health_text, encoding="utf-8")
    capture_nvidia_smi(artifact_dir / "nvidia-smi-serving.txt")

    models_record = request(models_url, timeout=10)
    if not 200 <= int(models_record["status_code"]) < 300:
        raise RuntimeError(
            f"/v1/models failed: {models_record['status_code']} {models_record['body']!r}"
        )
    try:
        models_body = json.loads(str(models_record["body"]))
    except json.JSONDecodeError as error:
        raise RuntimeError("/v1/models returned invalid JSON") from error
    write_json(artifact_dir / "models-response.json", models_body)
    returned = [item.get("id") for item in models_body.get("data", []) if isinstance(item, dict)]
    if args.model_id not in returned:
        raise RuntimeError(f"requested model is absent from /v1/models: {returned}")

    result = {
        "status": "passed",
        "health_http_status": health["status_code"],
        "health_attempts": attempts,
        "models_http_status": models_record["status_code"],
        "models_returned": returned,
        "model_listed": True,
        "server_startup_seconds": time.time() - args.server_launch_epoch,
        "finished_at_utc": timestamp(),
    }
    write_json(artifact_dir / "server-probe.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def gpu_evidence(artifact_dir: Path) -> dict[str, object]:
    gpu_name = "unknown"
    total_memory_mib: int | None = None
    driver = "unknown"
    info_path = artifact_dir / "gpu-info.txt"
    if info_path.is_file():
        fields = [field.strip() for field in info_path.read_text(encoding="utf-8").split(",")]
        if len(fields) >= 3:
            gpu_name, memory_text, driver = fields[:3]
            try:
                total_memory_mib = int(float(memory_text))
            except ValueError:
                total_memory_mib = None

    memory_values: list[int] = []
    for name in ("nvidia-smi-before.txt", "nvidia-smi-serving.txt", "nvidia-smi-after.txt"):
        path = artifact_dir / name
        if not path.is_file():
            continue
        memory_values.extend(
            int(value)
            for value in re.findall(r"(\d+)MiB\s*/\s*\d+MiB", path.read_text(encoding="utf-8"))
        )
    return {
        "name": gpu_name,
        "total_memory_mib": total_memory_mib,
        "driver_version": driver,
        "peak_observed_memory_mib": max(memory_values, default=None),
    }


def finalize(args: argparse.Namespace) -> int:
    artifact_dir: Path = args.artifact_dir
    agent_dir = artifact_dir / "agent-run"
    if not agent_dir.is_dir():
        agent_dir = artifact_dir
    run = load_json(agent_dir / "run.json")
    probe = load_json(artifact_dir / "server-probe.json")
    cleanup_text = (artifact_dir / "process-cleanup.txt").read_text(encoding="utf-8") if (
        artifact_dir / "process-cleanup.txt"
    ).is_file() else ""
    clean_shutdown = "graceful_termination_confirmed" in cleanup_text
    no_process_remained = "no_server_process_remains" in cleanup_text and "no_agent_process_remains" in cleanup_text
    server_success = probe.get("status") == "passed"
    adapter_events = (
        (agent_dir / "adapter-events.jsonl").read_text(encoding="utf-8")
        if (agent_dir / "adapter-events.jsonl").is_file()
        else ""
    )
    agent_initialized = '"event": "agent_initialized"' in adapter_events
    reported_classification = run.get("final_classification", "infrastructure_failure")
    classification = correct_post_server_classification(
        reported_classification,
        server_started=bool(probe),
        server_healthy=server_success,
        agent_launched=run.get("agent_configuration", {}).get("launches") == 1,
    )
    functional_success = classification == "secure_functional_success"
    dimensions = classification_dimensions(
        classification,
        server_started=bool(probe),
        server_healthy=server_success,
        agent_initialized=agent_initialized,
        final_tests_passed=run.get("after_test_exit_code") == 0,
    )
    success = (
        args.slurm_exit_status == 0
        and args.agent_process_exit == 0
        and functional_success
        and server_success
        and clean_shutdown
        and no_process_remained
    )

    result = {
        "schema": "mini-swe-agent-smoke-v1",
        "status": "passed" if success else "failed",
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": (artifact_dir / "hostname.txt").read_text(encoding="utf-8").strip() if (
            artifact_dir / "hostname.txt"
        ).is_file() else None,
        "git_commit": (artifact_dir / "git-commit.txt").read_text(encoding="utf-8").strip() if (
            artifact_dir / "git-commit.txt"
        ).is_file() else None,
        "gpu": gpu_evidence(artifact_dir),
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "mini_swe_agent_version": run.get("mini_swe_agent_version"),
        "initial_test_exit_code": run.get("before_test_exit_code"),
        "final_test_exit_code": run.get("after_test_exit_code"),
        "agent_process_exit_code": args.agent_process_exit,
        "agent_exit_status": run.get("agent_exit_code"),
        "termination_reason": run.get("termination_reason"),
        "agent_steps": run.get("agent_steps"),
        "model_request_count": run.get("model_request_count"),
        "command_count": run.get("command_count"),
        "prompt_tokens": run.get("usage_prompt"),
        "completion_tokens": run.get("usage_completion"),
        "total_tokens": run.get("usage_total"),
        "agent_started_at_utc": run.get("started_at_utc"),
        "agent_finished_at_utc": run.get("finished_at_utc"),
        "agent_wall_time_seconds": run.get("agent_wall_time_seconds"),
        "patch_sha256": run.get("patch_sha256"),
        "trajectory_sha256": run.get("trajectory_sha256"),
        "repository_inspected": run.get("repository_inspected"),
        "files_inspected": run.get("files_inspected", []),
        "functional_success": functional_success,
        "classification": classification,
        "reported_classification": reported_classification,
        "dimensions": dimensions,
        "source_repository_unchanged": load_json(agent_dir / "classification.json")
        .get("success_checks", {})
        .get("source_template_unchanged"),
        "agent_artifact_directory": str(agent_dir),
        "health_http_status": probe.get("health_http_status"),
        "models_http_status": probe.get("models_http_status"),
        "server_startup_seconds": probe.get("server_startup_seconds"),
        "server_shutdown_clean": clean_shutdown,
        "any_process_remained": not no_process_remained,
        "slurm_script_exit_status_before_finalization": args.slurm_exit_status,
        "finished_at_utc": timestamp(),
    }
    write_json(artifact_dir / "result.json", result)
    write_json(
        artifact_dir / "classification.json",
        {
            "classification": classification,
            "reported_classification": reported_classification,
            "dimensions": dimensions,
            "reason": "post-server failures are separated from infrastructure",
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if success else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument("--artifact-dir", required=True, type=Path)
    probe.add_argument("--server-pid", required=True, type=int)
    probe.add_argument("--server-launch-epoch", required=True, type=float)
    probe.add_argument("--base-url", default="http://127.0.0.1:8000")
    probe.add_argument("--model-id", default=MODEL_ID)
    probe.add_argument("--startup-timeout", default=180, type=int)
    final = subparsers.add_parser("finalize")
    final.add_argument("--artifact-dir", required=True, type=Path)
    final.add_argument("--slurm-exit-status", required=True, type=int)
    final.add_argument("--agent-process-exit", required=True, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "probe":
        return probe_server(args)
    return finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
