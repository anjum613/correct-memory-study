#!/usr/bin/env python3
"""Run one bounded, non-scientific Devstral final-service lifecycle smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import DEVSTRAL_PRODUCTION_PROFILE  # noqa: E402
from cmpilot.final_experiment import write_new_canonical_json  # noqa: E402
from cmpilot.final_model_runtime import (  # noqa: E402
    DEVSTRAL_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS,
    DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS,
    POST_LAUNCH_HEALTH_TIMEOUT_SECONDS,
    DevstralModelService,
)


SCHEMA = "cmpilot-devstral-final-lifecycle-technical-smoke-v1"
SMOKE_ID = "devstral-final-lifecycle-prerun-v1"
BENIGN_REQUEST_TIMEOUT_SECONDS = 180
DEFAULT_ARTIFACT_ROOT = Path(
    "/home/s224049759/final-experiment-artifacts/"
    "devstral-final-lifecycle-prerun-smoke/v1"
)
BATCH_PATH = ROOT / "slurm/devstral_final_lifecycle_smoke.sbatch"
_JOB_ID = re.compile(r"[0-9]{1,20}")


class DevstralFinalLifecycleSmokeError(RuntimeError):
    """The bounded technical smoke could not run or prove its lifecycle."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(ROOT), *arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def build_preflight() -> dict[str, Any]:
    """Bind the smoke to a clean immutable runtime without touching a GPU."""

    static_inputs = DEVSTRAL_PRODUCTION_PROFILE.verify_static_inputs(ROOT)
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=all")
    checks = {
        "clean_project_worktree": status.returncode == 0 and not status.stdout,
        "project_commit_resolved": (
            commit.returncode == 0
            and re.fullmatch(r"[0-9a-f]{40}", commit.stdout.strip()) is not None
        ),
        "qualified_profile_static_inputs": bool(static_inputs),
        "scientific_family_absent": True,
        "target_task_absent": True,
    }
    return {
        "checks": checks,
        "model_id": DEVSTRAL_PRODUCTION_PROFILE.model_id,
        "model_revision": DEVSTRAL_PRODUCTION_PROFILE.model_revision,
        "pass": all(checks.values()),
        "project_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "runtime_identity": {
            "batch_script_sha256": _sha256_file(BATCH_PATH),
            "environment_verifier_sha256": _sha256_file(
                ROOT / "scripts/verify_devstral_environment.py"
            ),
            "final_model_runtime_sha256": _sha256_file(
                ROOT / "src/cmpilot/final_model_runtime.py"
            ),
            "smoke_runner_sha256": _sha256_file(Path(__file__)),
        },
        "schema": "cmpilot-devstral-final-lifecycle-smoke-preflight-v1",
        "scientific_evidence": False,
        "smoke_id": SMOKE_ID,
        "static_input_count": len(static_inputs),
        "timeout_budgets_seconds": {
            "benign_model_request": BENIGN_REQUEST_TIMEOUT_SECONDS,
            "gpu_allocation_probe": (
                DEVSTRAL_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS
            ),
            "post_launch_health": POST_LAUNCH_HEALTH_TIMEOUT_SECONDS,
            "runtime_attestation_outer": (
                DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS
            ),
        },
    }


def _response_record(
    *, status_code: int, body: bytes, request_sha256: str
) -> dict[str, Any]:
    response_sha256 = hashlib.sha256(body).hexdigest()
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    choices = payload.get("choices") if isinstance(payload, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    passed = (
        status_code == 200
        and isinstance(payload, dict)
        and payload.get("model") == DEVSTRAL_PRODUCTION_PROFILE.served_model_name
        and isinstance(content, str)
        and bool(content.strip())
    )
    return {
        "choice_count": len(choices) if isinstance(choices, list) else None,
        "model": payload.get("model") if isinstance(payload, dict) else None,
        "nonempty_content": isinstance(content, str) and bool(content.strip()),
        "pass": passed,
        "request_sha256": request_sha256,
        "response_sha256": response_sha256,
        "status_code": status_code,
    }


def benign_model_request(base_url: str) -> dict[str, Any]:
    """Send exactly one harmless liveness request and retain only metadata."""

    payload = {
        "max_tokens": 8,
        "messages": [
            {
                "content": "Reply with one short greeting.",
                "role": "user",
            }
        ],
        "model": DEVSTRAL_PRODUCTION_PROFILE.served_model_name,
        "temperature": 0,
    }
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    request_sha256 = hashlib.sha256(body).hexdigest()
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=BENIGN_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310 - loopback-only endpoint
            return _response_record(
                status_code=response.status,
                body=response.read(),
                request_sha256=request_sha256,
            )
    except HTTPError as error:
        return _response_record(
            status_code=error.code,
            body=error.read(),
            request_sha256=request_sha256,
        )
    except (URLError, OSError, TimeoutError) as error:
        return {
            "error": f"{type(error).__name__}: {error}",
            "pass": False,
            "request_sha256": request_sha256,
            "status_code": None,
        }


def _json_object(path: Path) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def run_smoke(*, artifact_root: Path, slurm_job_id: str) -> dict[str, Any]:
    if _JOB_ID.fullmatch(slurm_job_id) is None:
        raise DevstralFinalLifecycleSmokeError(
            "execution requires a numeric SLURM_JOB_ID"
        )
    root = Path(artifact_root)
    if not root.is_absolute() or root == Path("/") or root.is_symlink():
        raise DevstralFinalLifecycleSmokeError(
            "artifact root must be an absolute, non-root, non-symlink path"
        )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    attempt = (
        root
        / "jobs"
        / slurm_job_id
        / "attempts"
        / f"slurm-{slurm_job_id}-{SMOKE_ID}"
    )
    attempt.mkdir(parents=True, exist_ok=False, mode=0o700)
    preflight = build_preflight()
    write_new_canonical_json(attempt / "smoke-preflight.json", preflight)
    if preflight.get("pass") is not True:
        raise DevstralFinalLifecycleSmokeError("technical smoke preflight failed")

    service = DevstralModelService(
        profile=DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
    )
    request_record: Mapping[str, Any] = {"pass": False, "started": False}
    error_record: str | None = None
    try:
        base_url = service.start(
            attempt_directory=attempt,
            run_id=f"technical-smoke-{slurm_job_id}",
            slurm_job_id=slurm_job_id,
        )
        request_record = benign_model_request(base_url)
        write_new_canonical_json(
            attempt / "benign-model-request.json", request_record
        )
    except BaseException as error:
        error_record = f"{type(error).__name__}: {error}"
    try:
        shutdown = service.shutdown()
    except BaseException as error:
        shutdown = {
            "complete": False,
            "error": f"{type(error).__name__}: {error}",
            "pass": False,
        }

    gpu = _json_object(attempt / "gpu-allocation.json")
    integrity = _json_object(attempt / "runtime-integrity.json")
    startup = _json_object(attempt / "server-startup.json")
    health = _json_object(attempt / "server-health.json")
    models = _json_object(attempt / "server-models.json")
    checks = {
        "benign_model_request": request_record.get("pass") is True,
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
        "attempt_directory": str(attempt),
        "checks": checks,
        "error": error_record,
        "model_id": DEVSTRAL_PRODUCTION_PROFILE.model_id,
        "model_revision": DEVSTRAL_PRODUCTION_PROFILE.model_revision,
        "pass": all(checks.values()) and error_record is None,
        "schema": SCHEMA,
        "scientific_evidence": False,
        "slurm_job_id": slurm_job_id,
        "smoke_id": SMOKE_ID,
    }
    write_new_canonical_json(attempt / "technical-smoke-result.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
    )
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.preflight_only:
            result = build_preflight()
        else:
            result = run_smoke(
                artifact_root=arguments.artifact_root,
                slurm_job_id=os.environ.get("SLURM_JOB_ID", ""),
            )
    except (DevstralFinalLifecycleSmokeError, OSError, ValueError) as error:
        print(f"DEVSTRAL_FINAL_LIFECYCLE_SMOKE_FAILURE: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
