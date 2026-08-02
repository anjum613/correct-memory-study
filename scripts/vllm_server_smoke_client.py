#!/usr/bin/env python3
"""Exercise a local vLLM OpenAI-compatible server and preserve JSON evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
PROMPT = (
    "Write a concise Python function named safe_divide(a, b) that raises "
    "ValueError when b is zero and otherwise returns a / b. Return only the code."
)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write_json_once(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def probe_health(health_url: str) -> dict[str, object]:
    """Accept a vLLM health response without assuming it is JSON."""
    request = Request(health_url, method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = response.status
            headers = dict(response.headers.items())
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Health check failed: {error.code} {body!r}") from error

    health_record: dict[str, object] = {
        "status_code": status_code,
        "headers": headers,
        "content_type": headers.get("content-type") or headers.get("Content-Type"),
        "body": body,
        "response_text": body,
    }
    if not 200 <= status_code < 300:
        raise RuntimeError(f"Health check failed: {status_code} {body!r}")
    return health_record


def capture_nvidia_smi(path: Path) -> None:
    """Write an immutable diagnostic snapshot while the model is serving."""
    completed = subprocess.run(
        ["nvidia-smi"],
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    if completed.stderr:
        output += "\n--- stderr ---\n" + completed.stderr
    with path.open("x", encoding="utf-8") as handle:
        handle.write(output)
    if completed.returncode:
        raise RuntimeError(f"nvidia-smi failed with exit code {completed.returncode}")



def request_json(
    method: str, url: str, payload: dict | None = None
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed: object = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"non_json_error_body": body}
        return error.code, parsed


def has_zero_divisor_check(text: str) -> bool:
    return bool(re.search(r"\bif\s+(?:b\s*==\s*0|not\s+b)\s*:", text))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--server-pid", required=True, type=int)
    parser.add_argument("--server-launch-epoch", required=True, type=float)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--startup-timeout", default=180, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_dir: Path = args.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "result.json"
    result: dict[str, object] = {
        "schema": "vllm-server-smoke-v1",
        "status": "running",
        "model_id_requested": args.model_id,
        "server_pid": args.server_pid,
        "server_base_url": args.base_url,
        "started_at_utc": timestamp(),
    }

    try:
        health_url = args.base_url + "/health"
        deadline = time.monotonic() + args.startup_timeout
        health_attempts = 0
        while True:
            if not process_alive(args.server_pid):
                raise RuntimeError("server process exited before becoming healthy")
            health_attempts += 1
            try:
                health_record = probe_health(health_url)
                break
            except (URLError, TimeoutError) as error:
                result["last_health_request_error"] = str(error)
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("server did not become healthy within startup timeout")
            time.sleep(2)

        healthy_at = timestamp()
        capture_nvidia_smi(artifact_dir / "nvidia-smi-serving.txt")
        write_json_once(artifact_dir / "health_response.json", health_record)
        result.update(
            server_healthy=True,
            health_attempts=health_attempts,
            server_healthy_at_utc=healthy_at,
            server_startup_seconds=time.time() - args.server_launch_epoch,
            health=health_record,
            nvidia_smi_during_serving_captured=True,
        )

        models_status, models_body = request_json("GET", args.base_url + "/v1/models")
        write_json_once(artifact_dir / "models_response.json", models_body)
        if not 200 <= models_status < 300:
            raise RuntimeError(f"/v1/models returned HTTP {models_status}")
        model_ids = [
            item.get("id")
            for item in models_body.get("data", [])
            if isinstance(item, dict)
        ]
        model_listed = args.model_id in model_ids
        result.update(
            models_http_status=models_status,
            models_returned=model_ids,
            requested_model_listed=model_listed,
        )
        if not model_listed:
            raise RuntimeError("requested model is absent from /v1/models")

        payload = {
            "model": args.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise coding assistant.",
                },
                {"role": "user", "content": PROMPT},
            ],
            "temperature": 0,
            "max_tokens": 128,
        }
        request_started = timestamp()
        started = time.perf_counter()
        chat_status, chat_body = request_json(
            "POST", args.base_url + "/v1/chat/completions", payload
        )
        latency = time.perf_counter() - started
        request_finished = timestamp()
        write_json_once(artifact_dir / "chat_response.json", chat_body)
        if not 200 <= chat_status < 300:
            raise RuntimeError(f"/v1/chat/completions returned HTTP {chat_status}")

        choices = chat_body.get("choices", [])
        text = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                text = str(message.get("content", "")).strip()
        usage = chat_body.get("usage", {})
        parsed = {
            "request_started_at_utc": request_started,
            "request_finished_at_utc": request_finished,
            "http_status": chat_status,
            "model_returned": chat_body.get("model"),
            "response_id": chat_body.get("id"),
            "prompt_token_count": usage.get("prompt_tokens"),
            "completion_token_count": usage.get("completion_tokens"),
            "total_token_count": usage.get("total_tokens"),
            "request_latency_seconds": latency,
            "generated_text": text,
            "generated_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "contains_safe_divide": "safe_divide" in text,
            "contains_zero_divisor_check": has_zero_divisor_check(text),
            "contains_value_error": "ValueError" in text,
            "output_non_empty": bool(text),
        }
        write_json_once(artifact_dir / "parsed_result.json", parsed)
        result.update(chat=parsed)

        for key in (
            "output_non_empty",
            "contains_safe_divide",
            "contains_zero_divisor_check",
            "contains_value_error",
        ):
            if not parsed[key]:
                raise RuntimeError(f"validation failed: {key}")

        result.update(status="passed", finished_at_utc=timestamp())
        write_json_once(result_path, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        result.update(
            status="failed",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            finished_at_utc=timestamp(),
        )
        write_json_once(result_path, result)
        print(json.dumps(result, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
