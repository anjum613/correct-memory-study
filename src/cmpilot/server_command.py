"""Safe extraction and validation of frozen Qwen32B server argument arrays."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import BinaryIO, Sequence


COMMAND_ARRAY_SCHEMA = "qwen32b-vllm-argv-v2"
EXTRACTION_RESULT_SCHEMA = "server-command-extraction-result-v1"
EXTRACTION_PASS = "SERVER_COMMAND_EXTRACTION_PASS"
EXTRACTION_FAILURE = "SERVER_COMMAND_EXTRACTION_FAILURE"
EXTRACTION_DEPENDENCY_FAILURE = "SERVER_COMMAND_EXTRACTION_DEPENDENCY_FAILURE"

GUIDED_DECODING_BACKEND = "lm-format-enforcer"
BACKEND_OPTION = "--guided-decoding-backend"
VLLM_MODULE = "vllm.entrypoints.openai.api_server"
VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
QWEN32B_REVISION = "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
QWEN32B_SNAPSHOT = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    + QWEN32B_REVISION
)

_VALUE_OPTIONS = {
    "--dtype": "bfloat16",
    "--gpu-memory-utilization": "0.90",
    "--host": "127.0.0.1",
    "--max-model-len": "4096",
    "--max-num-seqs": "1",
    "--model": str(QWEN32B_SNAPSHOT),
    "--seed": "0",
    "--served-model-name": str(QWEN32B_SNAPSHOT),
    "--tensor-parallel-size": "2",
    "--tokenizer": str(QWEN32B_SNAPSHOT),
    BACKEND_OPTION: GUIDED_DECODING_BACKEND,
}
_PROHIBITED_OPTIONS = (
    "--cpu-offload",
    "--cpu-offload-gb",
    "--enable-lora",
    "--guided-decoding-backend=outlines",
    "--quantization",
    "--speculative-model",
)


class CommandExtractionError(ValueError):
    """The serialized or extracted server command violates the frozen contract."""


@dataclass(frozen=True)
class ExternalExecutable:
    """One declared load-gate executable assumption."""

    category: str
    mandatory: bool
    path: Path
    scopes: tuple[str, ...]
    verify_before_submission: bool = True


_EXTERNAL_EXECUTABLES = (
    ExternalExecutable("cluster-core", True, Path("/usr/bin/bash"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/cp"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/env"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/hostname"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/mkdir"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/printf"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/sha256sum"), ("cpu", "gpu")),
    ExternalExecutable("cluster-core", True, Path("/usr/bin/curl"), ("gpu",)),
    ExternalExecutable(
        "cluster-core",
        True,
        Path("/usr/bin/nvidia-smi"),
        ("gpu",),
        verify_before_submission=False,
    ),
    ExternalExecutable("project-environment", True, VLLM_PYTHON, ("cpu", "gpu")),
    ExternalExecutable("project-environment", True, CMPILOT_PYTHON, ("cpu",)),
    ExternalExecutable(
        "project-environment",
        True,
        Path("/home/s224049759/environments/vllm-smoke/bin/torchrun"),
        ("gpu",),
    ),
    ExternalExecutable(
        "optional-diagnostic", False, Path("/usr/bin/numactl"), ("cpu", "gpu")
    ),
)


def _json_value(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CommandExtractionError(f"JSONDecodeError: {error}") from error
    except UnicodeError as error:
        raise CommandExtractionError(f"UnicodeError: {error}") from error
    except OSError as error:
        raise CommandExtractionError(f"OSError: {error}") from error


def load_command_argv(path: Path) -> tuple[str, ...]:
    """Read a canonical top-level argv list, accepting the job-25335 record as legacy."""
    value = _json_value(path)
    if isinstance(value, dict):
        if "argv" not in value:
            raise CommandExtractionError("legacy command object is missing the argv field")
        value = value["argv"]
    if not isinstance(value, list):
        raise CommandExtractionError("server command JSON must be a top-level list")
    if not value:
        raise CommandExtractionError("server command list must be non-empty")
    arguments: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise CommandExtractionError(
                f"server command items must be strings; item {index} is {type(item).__name__}"
            )
        if "\0" in item:
            raise CommandExtractionError(
                f"server command item {index} contains a null byte"
            )
        arguments.append(item)
    if not arguments[0]:
        raise CommandExtractionError("server command first argument must be non-empty")
    return tuple(arguments)


def _option_value(command: Sequence[str], option: str) -> str:
    positions = [index for index, item in enumerate(command) if item == option]
    if len(positions) != 1:
        raise CommandExtractionError(
            f"mandatory option {option} must occur exactly once; found {len(positions)}"
        )
    position = positions[0]
    if position + 1 >= len(command):
        raise CommandExtractionError(f"mandatory option {option} has no value")
    return command[position + 1]


def expected_qwen32b_server_command(
    *,
    port: int,
    expected_python: Path = VLLM_PYTHON,
    expected_snapshot: Path = QWEN32B_SNAPSHOT,
) -> tuple[str, ...]:
    """Return the only accepted BF16 TP=2 load-gate argument vector."""
    if not 1 <= port <= 65535:
        raise CommandExtractionError(f"invalid loopback port: {port}")
    return (
        str(expected_python),
        "-m",
        VLLM_MODULE,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        str(expected_snapshot),
        "--tokenizer",
        str(expected_snapshot),
        "--served-model-name",
        str(expected_snapshot),
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


def validate_qwen32b_server_command(
    command: Sequence[str],
    *,
    expected_python: Path = VLLM_PYTHON,
    expected_snapshot: Path = QWEN32B_SNAPSHOT,
) -> tuple[str, ...]:
    """Fail closed unless *command* is the exact frozen Qwen32B server argv."""
    normalized = tuple(command)
    if not normalized:
        raise CommandExtractionError("server command list must be non-empty")
    if any(not isinstance(item, str) for item in normalized):
        raise CommandExtractionError("server command items must be strings")
    if any("\0" in item for item in normalized):
        raise CommandExtractionError("server command contains a null byte")
    if not normalized[0]:
        raise CommandExtractionError("server command first argument must be non-empty")
    if normalized[0] != str(expected_python):
        raise CommandExtractionError(
            f"unexpected Python executable {normalized[0]!r}; expected {str(expected_python)!r}"
        )
    if not expected_python.is_file() or not os.access(expected_python, os.X_OK):
        raise CommandExtractionError(
            f"expected Python executable is unavailable or not executable: {expected_python}"
        )
    if normalized.count("-m") != 1 or normalized[1:3] != ("-m", VLLM_MODULE):
        raise CommandExtractionError(
            f"server command must invoke -m {VLLM_MODULE} exactly once"
        )
    port_text = _option_value(normalized, "--port")
    try:
        port = int(port_text)
    except ValueError as error:
        raise CommandExtractionError(f"invalid server port: {port_text!r}") from error
    expected_values = dict(_VALUE_OPTIONS)
    expected_values.update(
        {
            "--model": str(expected_snapshot),
            "--served-model-name": str(expected_snapshot),
            "--tokenizer": str(expected_snapshot),
        }
    )
    for option, expected_value in expected_values.items():
        actual = _option_value(normalized, option)
        if actual != expected_value:
            raise CommandExtractionError(
                f"mandatory option {option} has value {actual!r}; expected {expected_value!r}"
            )
    if normalized.count("--enforce-eager") != 1:
        raise CommandExtractionError("--enforce-eager must occur exactly once")
    for item in normalized:
        lowered = item.casefold()
        if lowered == "outlines" or any(
            lowered == option or lowered.startswith(option + "=")
            for option in _PROHIBITED_OPTIONS
        ):
            raise CommandExtractionError(f"prohibited server argument: {item!r}")
        if any(term in lowered for term in ("snapshot_download", "mini-swe", "calculator")):
            raise CommandExtractionError(f"prohibited server command value: {item!r}")
    expected = expected_qwen32b_server_command(
        port=port,
        expected_python=expected_python,
        expected_snapshot=expected_snapshot,
    )
    if normalized != expected:
        raise CommandExtractionError(
            "server command does not exactly match the frozen Qwen32B argv"
        )
    return normalized


def encode_nul_delimited(command: Sequence[str]) -> bytes:
    """Encode arguments for lossless Bash ``mapfile -d ''`` transfer."""
    chunks: list[bytes] = []
    for index, argument in enumerate(command):
        if not isinstance(argument, str):
            raise CommandExtractionError(f"argument {index} is not a string")
        if "\0" in argument:
            raise CommandExtractionError(f"argument {index} contains a null byte")
        chunks.append(argument.encode("utf-8") + b"\0")
    return b"".join(chunks)


def audit_external_executables(
    *, scope: str, inside_job: bool
) -> dict[str, object]:
    """Audit declared CPU or GPU executable assumptions without requiring jq."""
    if scope not in {"cpu", "gpu"}:
        raise ValueError(f"unsupported dependency scope: {scope}")
    rows: list[dict[str, object]] = []
    missing_mandatory: list[str] = []
    for dependency in _EXTERNAL_EXECUTABLES:
        if scope not in dependency.scopes:
            continue
        present = dependency.path.is_file() and os.access(dependency.path, os.X_OK)
        deferred = (
            dependency.mandatory
            and not dependency.verify_before_submission
            and not inside_job
        )
        if deferred:
            status = "DEFERRED_TO_BATCH"
        elif present:
            status = "PRESENT"
        elif dependency.mandatory:
            status = "MISSING"
            missing_mandatory.append(str(dependency.path))
        else:
            status = "OPTIONAL_UNAVAILABLE"
        row = asdict(dependency)
        row["path"] = str(dependency.path)
        row["present"] = present
        row["status"] = status
        rows.append(row)
    return {
        "dependencies": rows,
        "inside_job": inside_job,
        "jq_required": False,
        "missing_mandatory": missing_mandatory,
        "pass": not missing_mandatory,
        "schema": "load-gate-external-executables-v1",
        "scope": scope,
    }


def classify_job_25335_extraction_failure(
    *, stderr: str, script: str
) -> dict[str, object]:
    """Classify the preserved jq/process-substitution failure from job 25335."""
    signatures = (
        "/usr/bin/jq: No such file or directory",
        "SERVER_CMD[0]: unbound variable",
    )
    dependency_failure = all(value in stderr for value in signatures) and all(
        value in script for value in ("/usr/bin/jq", "mapfile -t SERVER_CMD")
    )
    return {
        "dimensions": {
            "gpu_failure": False if dependency_failure else None,
            "guided_backend_failure": False if dependency_failure else None,
            "model_load_failure": False if dependency_failure else None,
            "model_oom": False if dependency_failure else None,
            "tensor_parallel_failure": False if dependency_failure else None,
            "vllm_failure": False if dependency_failure else None,
        },
        "label": (
            EXTRACTION_DEPENDENCY_FAILURE
            if dependency_failure
            else "SERVER_COMMAND_EXTRACTION_UNCLASSIFIED"
        ),
        "vllm_started": False if dependency_failure else None,
    }


def render_bash_command_extraction(
    *,
    command_json: Path,
    artifact_dir: Path,
    extractor: Path,
    python_path: Path = VLLM_PYTHON,
    expected_snapshot: Path = QWEN32B_SNAPSHOT,
) -> str:
    """Render fail-closed Bash that preserves status before indexing the array."""
    for name, path in {
        "command JSON": command_json,
        "artifact directory": artifact_dir,
        "extractor": extractor,
        "Python executable": python_path,
        "snapshot": expected_snapshot,
    }.items():
        if not path.is_absolute():
            raise ValueError(f"{name} path must be absolute: {path}")
    quote = shlex.quote
    return f"""# Canonical Qwen32B server-command extraction using Python JSON parsing.
SERVER_COMMAND_JSON={quote(str(command_json))}
SERVER_COMMAND_ARTIFACT_DIR={quote(str(artifact_dir))}
SERVER_COMMAND_EXTRACTOR={quote(str(extractor))}
SERVER_COMMAND_PYTHON={quote(str(python_path))}
SERVER_COMMAND_EXPECTED_SNAPSHOT={quote(str(expected_snapshot))}
SERVER_COMMAND_STDERR="$SERVER_COMMAND_ARTIFACT_DIR/server-command-extraction.stderr"
SERVER_COMMAND_OUTPUT="$SERVER_COMMAND_ARTIFACT_DIR/server-command-extracted.argv.nul"
SERVER_COMMAND_RESULT="$SERVER_COMMAND_ARTIFACT_DIR/server-command-extraction-result.json"
SERVER_COMMAND_CLASSIFICATION="$SERVER_COMMAND_ARTIFACT_DIR/server-command-extraction-classification.json"
SERVER_COMMAND_STATUS_FILE="$SERVER_COMMAND_ARTIFACT_DIR/server-command-extraction.exit-code"
declare -a SERVER_CMD=()

server_command_extraction_failure() {{
    local stage=$1
    /usr/bin/printf '{{"label":"{EXTRACTION_FAILURE}","stage":"%s"}}\\n' "$stage" \
        > "$SERVER_COMMAND_CLASSIFICATION"
    exit 79
}}

[[ -f "$SERVER_COMMAND_JSON" && -r "$SERVER_COMMAND_JSON" ]] || \
    server_command_extraction_failure input-unavailable
[[ -f "$SERVER_COMMAND_EXTRACTOR" && -r "$SERVER_COMMAND_EXTRACTOR" ]] || \
    server_command_extraction_failure extractor-unavailable
[[ -x "$SERVER_COMMAND_PYTHON" ]] || \
    server_command_extraction_failure python-unavailable
/usr/bin/cp -- "$SERVER_COMMAND_JSON" \
    "$SERVER_COMMAND_ARTIFACT_DIR/server-command-input-preserved.json"

set +e
"$SERVER_COMMAND_PYTHON" "$SERVER_COMMAND_EXTRACTOR" \
    --command-json "$SERVER_COMMAND_JSON" \
    --expected-python "$SERVER_COMMAND_PYTHON" \
    --expected-snapshot "$SERVER_COMMAND_EXPECTED_SNAPSHOT" \
    --result "$SERVER_COMMAND_RESULT" \
    > "$SERVER_COMMAND_OUTPUT" 2> "$SERVER_COMMAND_STDERR"
SERVER_COMMAND_EXTRACTION_STATUS=$?
set -e
/usr/bin/printf '%s\\n' "$SERVER_COMMAND_EXTRACTION_STATUS" \
    > "$SERVER_COMMAND_STATUS_FILE"
(( SERVER_COMMAND_EXTRACTION_STATUS == 0 )) || \
    server_command_extraction_failure python-extraction

mapfile -d '' -t SERVER_CMD < "$SERVER_COMMAND_OUTPUT" || \
    server_command_extraction_failure bash-mapfile
SERVER_COMMAND_COUNT=0
if declare -p SERVER_CMD >/dev/null 2>&1; then
    SERVER_COMMAND_COUNT=${{#SERVER_CMD[@]}}
fi
(( SERVER_COMMAND_COUNT > 0 )) || \
    server_command_extraction_failure empty-array
[[ -n "${{SERVER_CMD[0]-}}" ]] || \
    server_command_extraction_failure empty-executable
[[ -x "${{SERVER_CMD[0]-}}" ]] || \
    server_command_extraction_failure executable-unavailable
/usr/bin/printf '{{"argument_count":%s,"label":"{EXTRACTION_PASS}"}}\\n' \
    "$SERVER_COMMAND_COUNT" > "$SERVER_COMMAND_CLASSIFICATION"
"""


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def extract_command_cli(argv: Sequence[str] | None = None) -> int:
    """CLI used by non-interactive batch shells; stdout is NUL-delimited argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-json", type=Path, required=True)
    parser.add_argument("--expected-python", type=Path, default=VLLM_PYTHON)
    parser.add_argument("--expected-snapshot", type=Path, default=QWEN32B_SNAPSHOT)
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        command = load_command_argv(arguments.command_json)
        command = validate_qwen32b_server_command(
            command,
            expected_python=arguments.expected_python,
            expected_snapshot=arguments.expected_snapshot,
        )
        payload = encode_nul_delimited(command)
        result = {
            "argument_count": len(command),
            "command_input_sha256": hashlib.sha256(
                arguments.command_json.read_bytes()
            ).hexdigest(),
            "expected_python": str(arguments.expected_python),
            "expected_snapshot": str(arguments.expected_snapshot),
            "label": EXTRACTION_PASS,
            "schema": EXTRACTION_RESULT_SCHEMA,
        }
        status = 0
    except Exception as error:
        payload = b""
        result = {
            "error": f"{type(error).__name__}: {error}",
            "label": EXTRACTION_FAILURE,
            "schema": EXTRACTION_RESULT_SCHEMA,
        }
        print(f"{EXTRACTION_FAILURE}: {result['error']}", file=sys.stderr)
        status = 79
    try:
        _write_json(arguments.result, result)
    except OSError as error:
        print(f"{EXTRACTION_FAILURE}: cannot write result: {error}", file=sys.stderr)
        return 79
    if status == 0:
        output: BinaryIO = sys.stdout.buffer
        output.write(payload)
        output.flush()
    return status


__all__ = [
    "BACKEND_OPTION",
    "COMMAND_ARRAY_SCHEMA",
    "CMPILOT_PYTHON",
    "CommandExtractionError",
    "EXTRACTION_DEPENDENCY_FAILURE",
    "EXTRACTION_FAILURE",
    "EXTRACTION_PASS",
    "GUIDED_DECODING_BACKEND",
    "QWEN32B_REVISION",
    "QWEN32B_SNAPSHOT",
    "VLLM_PYTHON",
    "audit_external_executables",
    "classify_job_25335_extraction_failure",
    "encode_nul_delimited",
    "expected_qwen32b_server_command",
    "extract_command_cli",
    "load_command_argv",
    "render_bash_command_extraction",
    "validate_qwen32b_server_command",
]
