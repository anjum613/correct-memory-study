"""Fail-closed vLLM guided-backend selection for Qwen32B load gates."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
import shlex
import sys
from typing import Mapping, Sequence


GUIDED_DECODING_BACKEND = "lm-format-enforcer"
BACKEND_OPTION = "--guided-decoding-backend"
PREFLIGHT_IMPORT = (
    "vllm.model_executor.guided_decoding.lm_format_enforcer_decoding"
)
PREFLIGHT_PASS = "GUIDED_BACKEND_PREFLIGHT_PASS"
PREFLIGHT_FAIL = "GUIDED_BACKEND_PREFLIGHT_FAIL"
DEPENDENCY_FAILURE = "GUIDED_BACKEND_DEPENDENCY_FAILURE"

VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
QWEN32B_REVISION = "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
QWEN32B_SNAPSHOT = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    + QWEN32B_REVISION
)

GUIDANCE_REQUEST_FIELDS = frozenset(
    {
        "guided_choice",
        "guided_decoding_backend",
        "guided_grammar",
        "guided_json",
        "guided_regex",
        "guided_whitespace_pattern",
        "response_format",
        "tool_choice",
        "tools",
    }
)


class GuidedBackendError(RuntimeError):
    """The generated command or request violates the backend contract."""


@dataclass(frozen=True)
class LoadGatePlanPaths:
    command_json: Path
    command_text: Path
    effective_configuration: Path
    request_json: Path
    run_manifest: Path


def offline_environment() -> dict[str, str]:
    """Return only the frozen, offline Hugging Face settings used by the gate."""
    return {
        "HF_HOME": "/home/s224049759/model-cache/huggingface",
        "HF_HUB_CACHE": "/home/s224049759/model-cache/huggingface/hub",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def _backend_positions(command: Sequence[str]) -> list[int]:
    positions: list[int] = []
    for index, argument in enumerate(command):
        if argument == BACKEND_OPTION or argument.startswith(BACKEND_OPTION + "="):
            positions.append(index)
    return positions


def _selected_backend(command: Sequence[str]) -> str:
    positions = _backend_positions(command)
    if len(positions) != 1:
        raise GuidedBackendError(
            f"expected exactly one {BACKEND_OPTION}, found {len(positions)}"
        )
    position = positions[0]
    argument = command[position]
    if argument == BACKEND_OPTION:
        if position + 1 >= len(command):
            raise GuidedBackendError(f"{BACKEND_OPTION} has no value")
        return command[position + 1]
    return argument.split("=", 1)[1]


def validate_lm_format_enforcer_command(command: Sequence[str]) -> tuple[str, ...]:
    """Validate explicit, singular lm-format-enforcer selection."""
    normalized = tuple(str(argument) for argument in command)
    if not normalized or not Path(normalized[0]).is_absolute():
        raise GuidedBackendError("the vLLM executable path must be absolute")
    backend = _selected_backend(normalized)
    if backend != GUIDED_DECODING_BACKEND:
        raise GuidedBackendError(
            f"selected backend {backend!r}; required {GUIDED_DECODING_BACKEND!r}"
        )
    if "outlines" in normalized:
        raise GuidedBackendError("the server command must not select outlines")
    return normalized


def select_lm_format_enforcer(command: Sequence[str]) -> tuple[str, ...]:
    """Append the explicit backend only when an otherwise-valid command omits it."""
    normalized = tuple(str(argument) for argument in command)
    positions = _backend_positions(normalized)
    if not positions:
        normalized += (BACKEND_OPTION, GUIDED_DECODING_BACKEND)
    return validate_lm_format_enforcer_command(normalized)


def build_qwen32b_server_command(
    *,
    port: int,
    python_path: Path = VLLM_PYTHON,
    snapshot: Path = QWEN32B_SNAPSHOT,
) -> tuple[str, ...]:
    """Build the exact frozen BF16 TP=2 Qwen32B load-only server command."""
    if not 1 <= port <= 65535:
        raise GuidedBackendError(f"invalid loopback port: {port}")
    if not python_path.is_absolute() or not snapshot.is_absolute():
        raise GuidedBackendError("interpreter and snapshot paths must be absolute")
    command = (
        str(python_path),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        str(snapshot),
        "--tokenizer",
        str(snapshot),
        "--served-model-name",
        str(snapshot),
        "--dtype",
        "bfloat16",
        "--tensor-parallel-size",
        "2",
        "--max-model-len",
        "4096",
        "--max-num-seqs",
        "1",
        "--gpu-memory-utilization",
        "0.90",
        "--seed",
        "0",
        "--enforce-eager",
        BACKEND_OPTION,
        GUIDED_DECODING_BACKEND,
    )
    return validate_lm_format_enforcer_command(command)


def minimal_chat_request(*, model: Path = QWEN32B_SNAPSHOT) -> dict[str, object]:
    """Return the unchanged ordinary request schema used by the load gate."""
    return {
        "max_tokens": 8,
        "messages": [
            {"role": "system", "content": "You are a concise coding assistant."},
            {"role": "user", "content": "Reply with only the word READY."},
        ],
        "model": str(model),
        "n": 1,
        "seed": 0,
        "stream": False,
        "temperature": 0,
    }


def validate_no_guidance_request(request: Mapping[str, object]) -> None:
    """Reject fields that could opt an ordinary request into guided decoding."""
    present = sorted(GUIDANCE_REQUEST_FIELDS.intersection(request))
    if present:
        raise GuidedBackendError(
            "ordinary request contains guided-decoding fields: " + ", ".join(present)
        )


def _option_value(command: Sequence[str], option: str) -> str:
    try:
        position = command.index(option)
    except ValueError as error:
        raise GuidedBackendError(f"server command omits {option}") from error
    if position + 1 >= len(command):
        raise GuidedBackendError(f"server command has no value for {option}")
    return command[position + 1]


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_json_bytes(value))


def write_qwen32b_load_gate_plan(
    artifact_dir: Path,
    *,
    port: int,
    python_path: Path = VLLM_PYTHON,
    snapshot: Path = QWEN32B_SNAPSHOT,
) -> LoadGatePlanPaths:
    """Write deterministic command, request, configuration, and manifest records."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    command = build_qwen32b_server_command(
        port=port, python_path=python_path, snapshot=snapshot
    )
    request = minimal_chat_request(model=snapshot)
    validate_no_guidance_request(request)
    environment = offline_environment()
    command_record = {
        "argv": list(command),
        "guided_decoding_backend": GUIDED_DECODING_BACKEND,
        "schema": "qwen32b-vllm-command-v1",
        "shell": shlex.join(command),
    }
    configuration = {
        "dtype": "bfloat16",
        "enforce_eager": True,
        "gpu_memory_utilization": "0.90",
        "guided_decoding_backend": GUIDED_DECODING_BACKEND,
        "host": "127.0.0.1",
        "max_model_len": 4096,
        "max_num_seqs": 1,
        "model": str(snapshot),
        "model_revision": QWEN32B_REVISION,
        "offline_environment": environment,
        "port": port,
        "python": str(python_path),
        "schema": "qwen32b-load-gate-effective-configuration-v1",
        "seed": 0,
        "tensor_parallel_size": 2,
        "tokenizer": str(snapshot),
        "trust_remote_code": False,
    }
    command_bytes = _json_bytes(command_record)
    request_bytes = _json_bytes(request)
    paths = LoadGatePlanPaths(
        command_json=artifact_dir / "server-command.json",
        command_text=artifact_dir / "server-command.txt",
        effective_configuration=artifact_dir / "effective-configuration.json",
        request_json=artifact_dir / "minimal-request.canonical.json",
        run_manifest=artifact_dir / "run-manifest.json",
    )
    manifest = {
        "effective_configuration": paths.effective_configuration.name,
        "guided_decoding_backend": GUIDED_DECODING_BACKEND,
        "minimal_request": paths.request_json.name,
        "minimal_request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "model_revision": QWEN32B_REVISION,
        "ordinary_request_has_guidance": False,
        "schema": "qwen32b-load-gate-plan-v1",
        "server_command": paths.command_json.name,
        "server_command_sha256": hashlib.sha256(command_bytes).hexdigest(),
    }
    paths.command_json.write_bytes(command_bytes)
    paths.command_text.write_text(shlex.join(command) + "\n", encoding="utf-8", newline="\n")
    _write_json(paths.effective_configuration, configuration)
    paths.request_json.write_bytes(request_bytes)
    _write_json(paths.run_manifest, manifest)
    return paths


def _forbidden_loaded_modules() -> list[str]:
    return sorted(
        name
        for name in sys.modules
        if name == "outlines"
        or name.startswith("outlines.")
        or name == "pyairports"
        or name.startswith("pyairports.")
    )


def run_backend_preflight(
    command: Sequence[str],
    request: Mapping[str, object],
    *,
    tokenizer_path: Path,
) -> dict[str, object]:
    """Exercise the ordinary lm-format-enforcer path without loading model tensors."""
    validated_command = validate_lm_format_enforcer_command(command)
    validate_no_guidance_request(request)
    if not tokenizer_path.is_absolute() or not tokenizer_path.is_dir():
        raise GuidedBackendError(f"local tokenizer snapshot is unavailable: {tokenizer_path}")

    modules_before = sorted(sys.modules)
    module = importlib.import_module(PREFLIGHT_IMPORT)
    from transformers import AutoTokenizer
    from vllm.entrypoints.openai.protocol import ChatCompletionRequest
    from vllm.model_executor.guided_decoding import (
        get_guided_decoding_logits_processor,
    )

    chat_request = ChatCompletionRequest(**dict(request))
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    processor = asyncio.run(
        get_guided_decoding_logits_processor(
            GUIDED_DECODING_BACKEND, chat_request, tokenizer
        )
    )
    modules_after = sorted(sys.modules)
    forbidden = _forbidden_loaded_modules()
    if processor is not None:
        raise GuidedBackendError("ordinary request unexpectedly created a logits processor")
    if forbidden:
        raise GuidedBackendError(
            "passing backend path imported forbidden modules: " + ", ".join(forbidden)
        )
    return {
        "command": list(validated_command),
        "forbidden_modules": forbidden,
        "guided_decoding_backend": GUIDED_DECODING_BACKEND,
        "import_path": PREFLIGHT_IMPORT,
        "import_result": "PASS" if module is not None else "FAIL",
        "label": PREFLIGHT_PASS,
        "modules_added": sorted(set(modules_after) - set(modules_before)),
        "modules_after": modules_after,
        "modules_before": modules_before,
        "ordinary_request_has_guidance": False,
        "processor_is_none": processor is None,
        "schema": "guided-backend-preflight-v1",
    }


def classify_load_gate_traceback(traceback_text: str) -> dict[str, object]:
    """Classify the exact dependency-boundary failure seen in job 25042."""
    signatures = (
        "vllm/model_executor/guided_decoding/outlines_decoding.py",
        "outlines/types/airports.py",
        "from pyairports.airports import AIRPORT_LIST",
        "ModuleNotFoundError: No module named 'pyairports'",
    )
    dependency_failure = all(signature in traceback_text for signature in signatures)
    return {
        "dimensions": {
            "gpu_failure": False if dependency_failure else None,
            "model_content_failure": False if dependency_failure else None,
            "model_load_failure": False if dependency_failure else None,
            "model_oom": False if dependency_failure else None,
            "tensor_parallel_failure": False if dependency_failure else None,
        },
        "label": DEPENDENCY_FAILURE if dependency_failure else "UNCLASSIFIED_TECHNICAL_FAILURE",
    }


def _read_command(path: Path) -> tuple[str, ...]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("argv"), list):
        raise GuidedBackendError("command record must contain an argv list")
    return tuple(str(argument) for argument in record["argv"])


def _generate_command(arguments: argparse.Namespace) -> int:
    paths = write_qwen32b_load_gate_plan(
        arguments.artifact_dir,
        port=arguments.port,
        python_path=arguments.python,
        snapshot=arguments.snapshot,
    )
    print(paths.run_manifest)
    return 0


def _preflight_command(arguments: argparse.Namespace) -> int:
    try:
        command = _read_command(arguments.command)
        request = json.loads(arguments.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise GuidedBackendError("request record must be a JSON object")
        result = run_backend_preflight(
            command, request, tokenizer_path=arguments.tokenizer
        )
        status = 0
    except Exception as error:
        result = {
            "error": f"{type(error).__name__}: {error}",
            "guided_decoding_backend": GUIDED_DECODING_BACKEND,
            "import_path": PREFLIGHT_IMPORT,
            "label": PREFLIGHT_FAIL,
            "schema": "guided-backend-preflight-v1",
        }
        status = 78
    _write_json(arguments.result, result)
    print(result["label"], file=sys.stderr if status else sys.stdout)
    return status


def _classify_command(arguments: argparse.Namespace) -> int:
    result = classify_load_gate_traceback(arguments.traceback.read_text(encoding="utf-8"))
    _write_json(arguments.result, result)
    print(result["label"])
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command_name", required=True)

    generate = commands.add_parser("generate", help="write a frozen Qwen32B load-gate plan")
    generate.add_argument("--artifact-dir", type=Path, required=True)
    generate.add_argument("--port", type=int, required=True)
    generate.add_argument("--python", type=Path, default=VLLM_PYTHON)
    generate.add_argument("--snapshot", type=Path, default=QWEN32B_SNAPSHOT)
    generate.set_defaults(handler=_generate_command)

    preflight = commands.add_parser("preflight", help="run the CPU backend gate")
    preflight.add_argument("--command", type=Path, required=True)
    preflight.add_argument("--request", type=Path, required=True)
    preflight.add_argument("--tokenizer", type=Path, required=True)
    preflight.add_argument("--result", type=Path, required=True)
    preflight.set_defaults(handler=_preflight_command)

    classify = commands.add_parser("classify", help="classify a preserved traceback")
    classify.add_argument("--traceback", type=Path, required=True)
    classify.add_argument("--result", type=Path, required=True)
    classify.set_defaults(handler=_classify_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except GuidedBackendError as error:
        print(f"{PREFLIGHT_FAIL}: {error}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
