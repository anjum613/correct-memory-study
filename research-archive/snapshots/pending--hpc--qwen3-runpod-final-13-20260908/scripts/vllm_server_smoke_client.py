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


def response_headers(response: object) -> dict[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    return {str(name): str(value) for name, value in headers.items()}


def http_response_record(
    status_code: int, headers: dict[str, str], body: str
) -> dict[str, object]:
    return {
        "status_code": status_code,
        "headers": headers,
        "content_type": headers.get("content-type") or headers.get("Content-Type"),
        "body": body,
        "response_text": body,
    }


def request_http(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 10,
) -> dict[str, object]:
    """Return raw HTTP evidence without parsing an endpoint response body."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return http_response_record(
                response.status, response_headers(response), body
            )
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return http_response_record(error.code, response_headers(error), body)


def response_status(record: dict[str, object]) -> int:
    return int(record["status_code"])


def require_2xx(endpoint: str, record: dict[str, object]) -> None:
    status_code = response_status(record)
    if not 200 <= status_code < 300:
        raise RuntimeError(
            f"{endpoint} failed: {status_code} {str(record['body'])!r}"
        )


def parse_json_response(endpoint: str, record: dict[str, object]) -> object:
    """Parse a successful JSON response only after its status is validated."""
    require_2xx(endpoint, record)
    try:
        return json.loads(str(record["body"]))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{endpoint} returned invalid JSON") from error



def probe_health(health_url: str) -> dict[str, object]:
    """Fetch a health response without assuming its successful body is JSON."""
    return request_http("GET", health_url, timeout=5)


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





def has_zero_divisor_check(text: str) -> bool:
    return bool(re.search(r"\bif\s+(?:b\s*==\s*0|not\s+b)\s*:", text))


def parse_chat_completion(
    chat_body: object,
    http_status: int,
    request_started: str,
    request_finished: str,
    request_latency_seconds: float,
) -> dict[str, object]:
    if not isinstance(chat_body, dict):
        raise RuntimeError("/v1/chat/completions returned a non-object JSON response")

    choices = chat_body.get("choices", [])
    text = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict):
            text = str(message.get("content", "")).strip()
    usage = chat_body.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return {
        "request_started_at_utc": request_started,
        "request_finished_at_utc": request_finished,
        "http_status": http_status,
        "model_returned": chat_body.get("model"),
        "response_id": chat_body.get("id"),
        "prompt_token_count": usage.get("prompt_tokens"),
        "completion_token_count": usage.get("completion_tokens"),
        "total_token_count": usage.get("total_tokens"),
        "request_latency_seconds": request_latency_seconds,
        "generated_text": text,
        "generated_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "contains_safe_divide": "safe_divide" in text,
        "contains_zero_divisor_check": has_zero_divisor_check(text),
        "contains_value_error": "ValueError" in text,
        "output_non_empty": bool(text),
    }



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
            except (URLError, TimeoutError) as error:
                result["last_health_request_error"] = str(error)
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "server did not become healthy within startup timeout"
                    ) from error
                time.sleep(2)
                continue

            write_json_once(artifact_dir / "health_response.json", health_record)
            if not 200 <= response_status(health_record) < 300:
                result.update(failure_stage="/health", health=health_record)
                require_2xx("/health", health_record)
            break

        healthy_at = timestamp()
        capture_nvidia_smi(artifact_dir / "nvidia-smi-serving.txt")
        result.update(
            server_healthy=True,
            health_attempts=health_attempts,
            server_healthy_at_utc=healthy_at,
            server_startup_seconds=time.time() - args.server_launch_epoch,
            health=health_record,
            nvidia_smi_during_serving_captured=True,
        )

        models_endpoint = args.base_url + "/v1/models"
        try:
            models_record = request_http("GET", models_endpoint)
        except (URLError, TimeoutError) as error:
            result.update(
                failure_stage="/v1/models request", models_request_error=repr(error)
            )
            raise
        write_json_once(artifact_dir / "models_http_response.json", models_record)
        result["models_http_response"] = models_record
        if not 200 <= response_status(models_record) < 300:
            result["failure_stage"] = "/v1/models"
            require_2xx("/v1/models", models_record)
        try:
            models_body = parse_json_response("/v1/models", models_record)
        except Exception:
            result["failure_stage"] = "/v1/models JSON parsing"
            raise
        if not isinstance(models_body, dict):
            result["failure_stage"] = "/v1/models JSON parsing"
            raise RuntimeError("/v1/models returned a non-object JSON response")
        write_json_once(artifact_dir / "models_response.json", models_body)
        model_ids = [
            item.get("id")
            for item in models_body.get("data", [])
            if isinstance(item, dict)
        ]
        model_listed = args.model_id in model_ids
        result.update(
            models_http_status=response_status(models_record),
            models_returned=model_ids,
            requested_model_listed=model_listed,
        )
        if not model_listed:
            result["failure_stage"] = "/v1/models validation"
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
        capture_nvidia_smi(artifact_dir / "nvidia-smi-before-request.txt")
        request_started = timestamp()
        started = time.perf_counter()
        try:
            chat_record = request_http(
                "POST",
                args.base_url + "/v1/chat/completions",
                payload,
                timeout=180,
            )
        except (URLError, TimeoutError) as error:
            result.update(
                failure_stage="/v1/chat/completions request",
                chat_request_error=repr(error),
                request_started_at_utc=request_started,
                request_finished_at_utc=timestamp(),
            )
            raise
        latency = time.perf_counter() - started
        request_finished = timestamp()
        write_json_once(artifact_dir / "chat_http_response.json", chat_record)
        result.update(
            chat_http_response=chat_record,
            chat_request_started_at_utc=request_started,
            chat_request_finished_at_utc=request_finished,
            chat_request_latency_seconds=latency,
        )
        if not 200 <= response_status(chat_record) < 300:
            result["failure_stage"] = "/v1/chat/completions"
            require_2xx("/v1/chat/completions", chat_record)
        try:
            chat_body = parse_json_response("/v1/chat/completions", chat_record)
        except Exception:
            result["failure_stage"] = "/v1/chat/completions JSON parsing"
            raise
        write_json_once(artifact_dir / "chat_response.json", chat_body)
        parsed = parse_chat_completion(
            chat_body,
            response_status(chat_record),
            request_started,
            request_finished,
            latency,
        )
        write_json_once(artifact_dir / "parsed_result.json", parsed)
        result.update(chat=parsed)

        for key in (
            "output_non_empty",
            "contains_safe_divide",
            "contains_zero_divisor_check",
            "contains_value_error",
        ):
            if not parsed[key]:
                result["failure_stage"] = "/v1/chat/completions response validation"
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
