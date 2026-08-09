#!/usr/bin/env python3
"""Run one Qwen3.6 OpenAI-compatible request through the project transport."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.integrations.miniswe.openai_transport import (  # noqa: E402
    OpenAIChatTransport,
    normalize_message,
)
from cmpilot.integrations.miniswe.vllm_text_model import _response_parts  # noqa: E402
from cmpilot.qwen36_candidate import MODEL_ID, write_canonical_json  # noqa: E402


MESSAGES = [
    {
        "role": "system",
        "content": "This is a model-serving health check. Follow the short instruction.",
    },
    {"role": "user", "content": "Reply with exactly SMOKE_OK."},
]


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def get(url: str, *, timeout: float = 5) -> tuple[int, bytes, dict[str, str]]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return (
            response.status,
            response.read(),
            {str(key): str(value) for key, value in response.headers.items()},
        )


def gpu_memory_rows() -> list[dict[str, object]]:
    completed = subprocess.run(
        (
            "/usr/bin/nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows = []
    for line in completed.stdout.splitlines():
        index, name, total, used, free = [part.strip() for part in line.split(",")]
        rows.append(
            {
                "free_mib": int(free),
                "index": int(index),
                "name": name,
                "total_mib": int(total),
                "used_mib": int(used),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:49786/v1")
    parser.add_argument("--server-pid", required=True, type=int)
    parser.add_argument("--startup-timeout", default=1800, type=int)
    arguments = parser.parse_args()
    artifact = arguments.artifact_directory.resolve(strict=True)
    result_path = artifact / "smoke-client-result.json"
    result: dict[str, object] = {
        "completed_model_requests": 0,
        "model_id": MODEL_ID,
        "schema": "qwen36-load-request-smoke-client-v1",
        "started_at_utc": timestamp(),
        "status": "FAIL",
    }
    try:
        health_url = arguments.base_url.removesuffix("/v1") + "/health"
        deadline = time.monotonic() + arguments.startup_timeout
        attempts = 0
        while True:
            try:
                os.kill(arguments.server_pid, 0)
            except ProcessLookupError as error:
                raise RuntimeError("vLLM exited before becoming healthy") from error
            attempts += 1
            try:
                health_status, health_body, health_headers = get(health_url)
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("vLLM did not become healthy before timeout")
                time.sleep(2)
                continue
            if health_status == 200:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"/health returned HTTP {health_status}")
            time.sleep(2)
        write_canonical_json(
            artifact / "health-response.json",
            {
                "body_utf8": health_body.decode("utf-8", errors="replace"),
                "headers": health_headers,
                "status_code": health_status,
            },
            exclusive=True,
        )

        models_status, models_raw, models_headers = get(arguments.base_url + "/models")
        if models_status != 200:
            raise RuntimeError(f"/v1/models returned HTTP {models_status}")
        models = json.loads(models_raw)
        model_ids = [
            row.get("id")
            for row in models.get("data", [])
            if isinstance(row, dict)
        ]
        if MODEL_ID not in model_ids:
            raise RuntimeError(f"pinned model is absent from /v1/models: {model_ids}")
        write_canonical_json(
            artifact / "models-response.json",
            {
                "body": models,
                "headers": models_headers,
                "status_code": models_status,
            },
            exclusive=True,
        )

        memory = gpu_memory_rows()
        write_canonical_json(
            artifact / "gpu-memory-after-load.json", memory, exclusive=True
        )
        transport = OpenAIChatTransport(
            arguments.base_url,
            connect_timeout_seconds=10,
            read_timeout_seconds=300,
        )
        request_started = time.perf_counter()
        completion = transport.complete(
            MESSAGES,
            model=MODEL_ID,
            temperature=0.0,
            max_tokens=128,
        )
        latency = time.perf_counter() - request_started
        result["completed_model_requests"] = 1
        canonical, content, finish_reason = _response_parts(completion.body)
        normalized_response = normalize_message(
            completion.body["choices"][0]["message"],
            "$.response.choices[0].message",
        )
        if completion.status_code != 200 or not content.strip():
            raise RuntimeError("chat completion did not contain assistant content")
        request_record = {
            "request": completion.request,
            "request_sha256": completion.request_sha256,
        }
        response_record = {
            "body": completion.body,
            "canonical_assistant_message": canonical,
            "excluded_response_paths": list(normalized_response.excluded_paths),
            "finish_reason": finish_reason,
            "http_status": completion.status_code,
            "latency_seconds": latency,
            "raw_body": completion.raw_body,
            "response_sha256": completion.response_sha256,
        }
        write_canonical_json(
            artifact / "chat-request.json", request_record, exclusive=True
        )
        write_canonical_json(
            artifact / "chat-response.json", response_record, exclusive=True
        )
        result.update(
            canonical_response_parsed=True,
            direct_project_transport_used=True,
            exact_fixed_response=content.strip() == "SMOKE_OK",
            finished_at_utc=timestamp(),
            gpu_memory_after_load=memory,
            health_attempts=attempts,
            model_content=content,
            request_sha256=completion.request_sha256,
            response_sha256=completion.response_sha256,
            status="PASS",
        )
    except BaseException as error:
        result.update(
            error=f"{type(error).__name__}: {error}",
            finished_at_utc=timestamp(),
            traceback=traceback.format_exc(),
        )
    write_canonical_json(result_path, result, exclusive=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
