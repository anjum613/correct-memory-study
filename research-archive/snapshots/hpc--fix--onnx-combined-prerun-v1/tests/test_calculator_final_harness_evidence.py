from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
MINI_PYTHON = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)
TOKENIZER = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
)


def test_final_harness_evidence_is_exact_and_transport_free(tmp_path: Path) -> None:
    if not MINI_PYTHON.is_file():
        pytest.skip("dedicated mini-SWE environment is unavailable")
    output = tmp_path / "evidence.json"
    result = subprocess.run(
        [
            str(MINI_PYTHON),
            str(ROOT / "scripts" / "calculator_final_harness_evidence.py"),
            "--request-fixture",
            str(ROOT / "tests" / "fixtures" / "job_25642_request_15.json"),
            "--tokenizer",
            str(TOKENIZER),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["pass"] is True
    assert evidence["context_budget"]["prompt_tokens"] == 3696
    assert evidence["context_budget"]["effective_completion_limit"] == 368
    assert evidence["maximum_emitted_request_tokens"] == 4064
    assert evidence["maximum_with_safety_reserve"] == 4096
    assert evidence["context_exhaustion_http_calls"] == 0
    assert evidence["interactive_editor_shell_calls"] == 0
