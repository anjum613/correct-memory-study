from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from types import ModuleType


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm/qwen36_model_load_request_smoke.sbatch"
CLIENT = ROOT / "scripts/qwen36_smoke_client.py"
CONTRACT = ROOT / "qualification/qwen36-v1/smoke-interpreter-contract.json"
PROJECT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
QWEN36_PYTHON = Path("/home/s224049759/environments/qwen36-vllm-v1/bin/python")
MODEL_ID = "Qwen/Qwen3.6-27B"


def load_client() -> ModuleType:
    spec = importlib.util.spec_from_file_location("qwen36_smoke_client_test", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interpreter_contract_maps_every_smoke_runtime_role_explicitly() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    batch = BATCH.read_text(encoding="utf-8")
    helpers = {row["script"]: row for row in contract["helpers"]}

    assert contract["schema"] == "qwen36-smoke-interpreter-contract-v1"
    assert contract["interpreters"]["project_harness"] == {
        "environment_fingerprint": (
            "6325999d4038c8c93c1c313e10a66386a5afe803bf966a951317ff12a3d35128"
        ),
        "executable": str(PROJECT_PYTHON),
        "package_count": 10,
        "python_version": "3.11.15",
    }
    qwen = contract["interpreters"]["qwen36_runtime"]
    assert qwen["executable"] == str(QWEN36_PYTHON)
    assert qwen["environment_fingerprint"] == (
        "fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab"
    )
    assert qwen["content_digest"] == (
        "b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74"
    )
    assert helpers["scripts/qwen36_smoke_client.py"]["actual_launcher"] == "VLLM_PY"
    assert helpers["scripts/qwen36_gpu_probe.py"]["actual_launcher"] == "TORCHRUN"
    assert helpers["scripts/finalize_qwen36_smoke.py"]["actual_launcher"] == (
        "CMPILOT_PY"
    )
    assert f"CMPILOT_PY={PROJECT_PYTHON}" in batch
    assert f"VLLM_PY={QWEN36_PYTHON}" in batch


def test_smoke_client_uses_qwen36_python_and_never_the_incomplete_project_python() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    assert batch.count('"$VLLM_PY" "$PROJECT/scripts/qwen36_smoke_client.py"') == 1
    assert '"$CMPILOT_PY" "$PROJECT/scripts/qwen36_smoke_client.py"' not in batch
    assert "vllm_text_model" not in client
    project_probe = subprocess.run(
        (
            str(PROJECT_PYTHON),
            "-c",
            "import importlib.util; "
            "raise SystemExit(0 if importlib.util.find_spec('pydantic') is None else 1)",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert project_probe.returncode == 0


def test_smoke_client_imports_with_exact_frozen_qwen36_interpreter() -> None:
    completed = subprocess.run(
        (str(QWEN36_PYTHON), str(CLIENT), "--help"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "PYTHONNOUSERSITE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Run one Qwen3.6 OpenAI-compatible request" in completed.stdout


def test_qwen36_smoke_batch_has_no_unqualified_python_or_activation() -> None:
    batch = BATCH.read_text(encoding="utf-8")
    unqualified = re.compile(
        r"(?<![/A-Za-z0-9_.-])python(?:3(?:\.\d+)?)?(?=\s|$)"
    )

    assert unqualified.search(batch) is None
    assert "conda activate" not in batch
    assert "run_qualification_task.py" not in batch
    assert "qnm-p0" not in batch
    assert "memory-treatment" not in batch


class SmokeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict[str, object]] = []

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, value: object) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json({})
        elif self.path == "/v1/models":
            self.send_json({"data": [{"id": MODEL_ID}], "object": "list"})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append(json.loads(body))
        self.send_json(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "index": 0,
                        "message": {
                            "content": "SMOKE_OK",
                            "reasoning_content": "synthetic reasoning",
                            "role": "assistant",
                        },
                    }
                ],
                "id": "synthetic-smoke",
                "model": MODEL_ID,
                "object": "chat.completion",
                "usage": {
                    "completion_tokens": 2,
                    "prompt_tokens": 8,
                    "total_tokens": 10,
                },
            }
        )


def test_smoke_client_cpu_mock_exercises_request_and_reasoning_response(
    tmp_path: Path, monkeypatch: object
) -> None:
    client = load_client()
    SmokeHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(  # type: ignore[attr-defined]
        client,
        "gpu_memory_rows",
        lambda: [
            {
                "free_mib": 12000,
                "index": 0,
                "name": "NVIDIA A100-PCIE-40GB",
                "total_mib": 40960,
                "used_mib": 28960,
            }
        ],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sys,
        "argv",
        [
            str(CLIENT),
            "--artifact-directory",
            str(tmp_path),
            "--base-url",
            f"http://127.0.0.1:{server.server_port}/v1",
            "--server-pid",
            str(os.getpid()),
            "--startup-timeout",
            "5",
        ],
    )
    try:
        exit_code = client.main()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert exit_code == 0
    result = json.loads((tmp_path / "smoke-client-result.json").read_text())
    response = json.loads((tmp_path / "chat-response.json").read_text())
    assert result["status"] == "PASS"
    assert result["completed_model_requests"] == 1
    assert result["canonical_response_parsed"] is True
    assert result["exact_fixed_response"] is True
    assert result["model_content"] == "SMOKE_OK"
    assert response["finish_reason"] == "stop"
    assert response["canonical_assistant_message"] == {
        "content": "SMOKE_OK",
        "role": "assistant",
    }
    assert response["excluded_response_paths"] == [
        "$.response.choices[0].message.reasoning_content"
    ]
    assert SmokeHandler.requests == [
        {
            "max_tokens": 128,
            "messages": [
                {
                    "content": (
                        "This is a model-serving health check. Follow the short instruction."
                    ),
                    "role": "system",
                },
                {"content": "Reply with exactly SMOKE_OK.", "role": "user"},
            ],
            "model": MODEL_ID,
            "temperature": 0.0,
        }
    ]
