#!/usr/bin/env python3
"""Run one bounded, non-scientific Devstral final-service lifecycle smoke."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import DEVSTRAL_PRODUCTION_PROFILE  # noqa: E402
from cmpilot.final_experiment import write_new_canonical_json  # noqa: E402
from cmpilot.final_model_runtime import DevstralModelService  # noqa: E402


SMOKE_ID = "devstral-final-service-lifecycle-smoke-v1"
SMOKE_SCHEMA = "cmpilot-devstral-final-service-lifecycle-smoke-v1"
PREFLIGHT_SCHEMA = "cmpilot-devstral-final-service-smoke-preflight-v1"
BENIGN_PROMPT = "Reply with the single word READY."
MODEL_REQUEST_TIMEOUT_SECONDS = 120
PREFLIGHT_COMMAND_TIMEOUT_SECONDS = 300
MAX_RESPONSE_BYTES = 1024 * 1024
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_JOB_ID = re.compile(r"^[0-9]{1,20}$")


def _command(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(argv),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
    )


def build_preflight(
    *,
    attempt_directory: Path,
    expected_project_commit: str,
    job_id: str,
    environment: Mapping[str, str] | None = None,
    command_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = _command,
) -> dict[str, Any]:
    """Validate the immutable technical-smoke boundary without writing files."""

    observed_environment = dict(os.environ if environment is None else environment)
    attempt = Path(attempt_directory)
    expected_attempt_name = f"slurm-{job_id}-service-smoke-v1"
    checks = {
        "attempt_absent": not attempt.exists() and not attempt.is_symlink(),
        "attempt_identity": (
            _JOB_ID.fullmatch(job_id) is not None
            and attempt.name == expected_attempt_name
        ),
        "benign_prompt": BENIGN_PROMPT == "Reply with the single word READY.",
        "clean_project": False,
        "exact_project_commit": False,
        "model_profile_static_inputs": False,
        "numeric_slurm_job": _JOB_ID.fullmatch(job_id) is not None,
        "slurm_identity": observed_environment.get("SLURM_JOB_ID") == job_id,
    }
    diagnostics: dict[str, str] = {}
    head: str | None = None
    try:
        status = command_runner(("git", "status", "--porcelain"))
        checks["clean_project"] = status.returncode == 0 and not status.stdout
        diagnostics["clean_project"] = status.stderr.strip()
        revision = command_runner(("git", "rev-parse", "HEAD"))
        head = revision.stdout.strip() if revision.returncode == 0 else None
        checks["exact_project_commit"] = (
            _COMMIT.fullmatch(expected_project_commit) is not None
            and head == expected_project_commit
        )
        diagnostics["exact_project_commit"] = revision.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        diagnostics["git"] = f"{type(error).__name__}: {error}"
    try:
        DEVSTRAL_PRODUCTION_PROFILE.verify_static_inputs(ROOT)
        checks["model_profile_static_inputs"] = True
    except (OSError, ValueError) as error:
        diagnostics["model_profile_static_inputs"] = (
            f"{type(error).__name__}: {error}"
        )
    return {
        "attempt_directory": str(attempt),
        "checks": checks,
        "diagnostics": diagnostics,
        "expected_project_commit": expected_project_commit,
        "job_id": job_id,
        "model_profile": DEVSTRAL_PRODUCTION_PROFILE.profile_id,
        "observed_project_commit": head,
        "pass": all(checks.values()),
        "schema": PREFLIGHT_SCHEMA,
        "scientific_evidence": False,
        "side_effects": False,
        "smoke_id": SMOKE_ID,
    }


def _benign_model_request(base_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "max_tokens": 8,
        "messages": [{"content": BENIGN_PROMPT, "role": "user"}],
        "model": DEVSTRAL_PRODUCTION_PROFILE.served_model_name,
        "stream": False,
        "temperature": 0,
    }
    request_body = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    endpoint = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        endpoint,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=MODEL_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310 - loopback-only endpoint
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            status_code = response.status
    except HTTPError as error:
        response_body = error.read(MAX_RESPONSE_BYTES + 1)
        status_code = error.code
    except (OSError, TimeoutError, URLError) as error:
        raise RuntimeError(f"benign model request failed: {type(error).__name__}: {error}") from error
    if len(response_body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("benign model response exceeded the fixed 1 MiB bound")
    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("benign model response was not UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("benign model response was not a JSON object")
    choices = parsed.get("choices")
    passed = status_code == 200 and isinstance(choices, list) and bool(choices)
    record = {
        "endpoint": endpoint,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "pass": passed,
        "request_sha256": hashlib.sha256(request_body).hexdigest(),
        "response_sha256": hashlib.sha256(response_body).hexdigest(),
        "status_code": status_code,
        "timeout_seconds": MODEL_REQUEST_TIMEOUT_SECONDS,
    }
    if not passed:
        raise RuntimeError(f"benign model request did not succeed: {record}")
    return record, parsed


def _load_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def execute_smoke(
    *,
    attempt_directory: Path,
    job_id: str,
    service_factory: Callable[[], DevstralModelService] | None = None,
    request_sender: Callable[[str], tuple[dict[str, Any], dict[str, Any]]] = (
        _benign_model_request
    ),
) -> dict[str, Any]:
    """Execute the service-only smoke once and preserve total technical evidence."""

    attempt = Path(attempt_directory)
    attempt.parent.mkdir(parents=True, exist_ok=True)
    attempt.mkdir(mode=0o700)
    service = (
        service_factory()
        if service_factory is not None
        else DevstralModelService(
            profile=DEVSTRAL_PRODUCTION_PROFILE,
            project_root=ROOT,
        )
    )
    model_request: dict[str, Any] = {"pass": False}
    shutdown: Mapping[str, Any] = {"complete": False, "pass": False}
    error_text: str | None = None
    try:
        base_url = service.start(
            attempt_directory=attempt,
            run_id=SMOKE_ID,
            slurm_job_id=job_id,
        )
        model_request, response = request_sender(base_url)
        write_new_canonical_json(attempt / "benign-model-request.json", model_request)
        write_new_canonical_json(attempt / "benign-model-response.json", response)
    except BaseException as error:
        error_text = f"{type(error).__name__}: {error}"
    finally:
        try:
            shutdown = service.shutdown()
        except BaseException as error:
            shutdown = {
                "complete": False,
                "error": f"{type(error).__name__}: {error}",
                "pass": False,
            }
    gpu = _load_record(attempt / "gpu-allocation.json")
    integrity = _load_record(attempt / "runtime-integrity.json")
    startup = _load_record(attempt / "server-startup.json")
    health = _load_record(attempt / "server-health.json")
    models = _load_record(attempt / "server-models.json")
    checks = {
        "benign_model_request": model_request.get("pass") is True,
        "clean_shutdown": shutdown.get("pass") is True,
        "gpu_inspection": gpu.get("pass") is True,
        "models_endpoint": models.get("pass") is True,
        "post_launch_health_200": (
            health.get("pass") is True and health.get("status_code") == 200
        ),
        "runtime_attestation": integrity.get("pass") is True,
        "vllm_popen": startup.get("pass") is True and (attempt / "server.pid").is_file(),
    }
    result = {
        "attempt_directory": str(attempt.resolve()),
        "checks": checks,
        "error": error_text,
        "job_id": job_id,
        "model_id": DEVSTRAL_PRODUCTION_PROFILE.model_id,
        "model_profile": DEVSTRAL_PRODUCTION_PROFILE.profile_id,
        "model_request": model_request,
        "pass": all(checks.values()) and error_text is None,
        "schema": SMOKE_SCHEMA,
        "scientific_evidence": False,
        "shutdown": dict(shutdown),
        "smoke_id": SMOKE_ID,
    }
    write_new_canonical_json(attempt / "technical-smoke-result.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-directory", type=Path, required=True)
    parser.add_argument("--expected-project-commit", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    preflight = build_preflight(
        attempt_directory=arguments.attempt_directory,
        expected_project_commit=arguments.expected_project_commit,
        job_id=arguments.job_id,
    )
    if arguments.preflight_only or preflight["pass"] is not True:
        print(json.dumps(preflight, ensure_ascii=False, sort_keys=True))
        return 0 if preflight["pass"] is True else 1
    result = execute_smoke(
        attempt_directory=arguments.attempt_directory,
        job_id=arguments.job_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
