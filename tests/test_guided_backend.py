from __future__ import annotations

import importlib.abc
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from cmpilot.guided_backend import (
    BACKEND_OPTION,
    GUIDANCE_REQUEST_FIELDS,
    GUIDED_DECODING_BACKEND,
    QWEN32B_SNAPSHOT,
    build_qwen32b_server_command,
    classify_load_gate_traceback,
    minimal_chat_request,
    offline_environment,
    select_lm_format_enforcer,
    write_qwen32b_load_gate_plan,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")


def _option_value(command: tuple[str, ...], option: str) -> str:
    position = command.index(option)
    return command[position + 1]


def test_qwen32b_command_explicitly_selects_only_lm_format_enforcer() -> None:
    command = build_qwen32b_server_command(port=49773)

    assert command.count(BACKEND_OPTION) == 1
    assert _option_value(command, BACKEND_OPTION) == GUIDED_DECODING_BACKEND
    assert "outlines" not in command


def test_qwen32b_command_retains_frozen_load_configuration() -> None:
    command = build_qwen32b_server_command(port=49773)

    assert _option_value(command, "--model") == str(QWEN32B_SNAPSHOT)
    assert _option_value(command, "--tokenizer") == str(QWEN32B_SNAPSHOT)
    assert _option_value(command, "--served-model-name") == str(QWEN32B_SNAPSHOT)
    assert _option_value(command, "--host") == "127.0.0.1"
    assert _option_value(command, "--dtype") == "bfloat16"
    assert _option_value(command, "--tensor-parallel-size") == "2"
    assert _option_value(command, "--max-model-len") == "4096"
    assert _option_value(command, "--max-num-seqs") == "1"
    assert _option_value(command, "--gpu-memory-utilization") == "0.90"
    assert _option_value(command, "--seed") == "0"
    assert "--enforce-eager" in command
    assert not {"--quantization", "--cpu-offload-gb", "--enable-lora"}.intersection(command)
    environment = offline_environment()
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"


def test_correction_changes_only_backend_selection_for_job_25042() -> None:
    original = tuple(
        shlex.split((FIXTURES / "job_25042_server_command.txt").read_text(encoding="utf-8"))
    )
    corrected = select_lm_format_enforcer(original)

    assert BACKEND_OPTION not in original
    assert corrected[:-2] == original
    assert corrected[-2:] == (BACKEND_OPTION, GUIDED_DECODING_BACKEND)
    assert corrected == build_qwen32b_server_command(port=49773)


def test_minimal_request_schema_has_no_guidance_fields() -> None:
    request = minimal_chat_request()

    assert set(request) == {
        "max_tokens",
        "messages",
        "model",
        "n",
        "seed",
        "stream",
        "temperature",
    }
    assert set(request).isdisjoint(GUIDANCE_REQUEST_FIELDS)


def test_generated_plan_records_backend_command_request_and_offline_mode(
    tmp_path: Path,
) -> None:
    paths = write_qwen32b_load_gate_plan(tmp_path, port=49773)
    command = json.loads(paths.command_json.read_text(encoding="utf-8"))
    command_metadata = json.loads(paths.command_metadata.read_text(encoding="utf-8"))
    configuration = json.loads(paths.effective_configuration.read_text(encoding="utf-8"))
    manifest = json.loads(paths.run_manifest.read_text(encoding="utf-8"))
    request = json.loads(paths.request_json.read_text(encoding="utf-8"))

    assert command.count(BACKEND_OPTION) == 1
    assert command_metadata["argv_file"] == paths.command_json.name
    assert configuration["guided_decoding_backend"] == GUIDED_DECODING_BACKEND
    assert configuration["offline_environment"] == offline_environment()
    assert manifest["guided_decoding_backend"] == GUIDED_DECODING_BACKEND
    assert manifest["effective_configuration"] == paths.effective_configuration.name
    assert set(request).isdisjoint(GUIDANCE_REQUEST_FIELDS)


def test_lm_format_enforcer_normal_path_survives_broken_outlines_import(
    tmp_path: Path,
) -> None:
    assert VLLM_PYTHON.is_file()
    plan = write_qwen32b_load_gate_plan(tmp_path, port=49773)
    code = r'''
import importlib.abc
import json
import pathlib
import sys

class RejectBrokenBackends(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "outlines" or fullname.startswith("outlines."):
            raise ModuleNotFoundError("simulated broken outlines import")
        if fullname == "pyairports" or fullname.startswith("pyairports."):
            raise ModuleNotFoundError("simulated broken pyairports import")
        return None

sys.meta_path.insert(0, RejectBrokenBackends())
from cmpilot.guided_backend import run_backend_preflight

command = tuple(json.loads(pathlib.Path(sys.argv[1]).read_text()))
request = json.loads(pathlib.Path(sys.argv[2]).read_text())
result = run_backend_preflight(command, request, tokenizer_path=pathlib.Path(sys.argv[3]))
print("BACKEND_RESULT=" + json.dumps({
    "backend": result["guided_decoding_backend"],
    "forbidden_modules": result["forbidden_modules"],
    "import_result": result["import_result"],
    "processor_is_none": result["processor_is_none"],
}, sort_keys=True))
'''
    environment = os.environ.copy()
    environment.update(offline_environment())
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    completed = subprocess.run(
        [
            str(VLLM_PYTHON),
            "-c",
            code,
            str(plan.command_json),
            str(plan.request_json),
            str(QWEN32B_SNAPSHOT),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    result_line = next(
        (line for line in completed.stdout.splitlines() if line.startswith("BACKEND_RESULT=")),
        None,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result_line is not None
    result = json.loads(result_line.removeprefix("BACKEND_RESULT="))
    assert result == {
        "backend": GUIDED_DECODING_BACKEND,
        "forbidden_modules": [],
        "import_result": "PASS",
        "processor_is_none": True,
    }


def test_job_25042_traceback_is_guided_backend_dependency_failure() -> None:
    traceback_text = (FIXTURES / "job_25042_guided_backend_traceback.txt").read_text(
        encoding="utf-8"
    )
    classification = classify_load_gate_traceback(traceback_text)

    assert classification["label"] == "GUIDED_BACKEND_DEPENDENCY_FAILURE"
    assert classification["dimensions"] == {
        "gpu_failure": False,
        "model_content_failure": False,
        "model_load_failure": False,
        "model_oom": False,
        "tensor_parallel_failure": False,
    }
