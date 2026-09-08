from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from cmpilot.guided_backend import (
    BACKEND_OPTION,
    GUIDED_DECODING_BACKEND,
    QWEN32B_SNAPSHOT,
    VLLM_PYTHON,
    build_qwen32b_server_command,
    write_qwen32b_load_gate_plan,
)
from cmpilot.server_command import (
    COMMAND_ARRAY_SCHEMA,
    EXTRACTION_DEPENDENCY_FAILURE,
    EXTRACTION_FAILURE,
    CommandExtractionError,
    audit_external_executables,
    classify_job_25335_extraction_failure,
    encode_nul_delimited,
    load_command_argv,
    render_bash_command_extraction,
    validate_qwen32b_server_command,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
EXTRACTOR = ROOT / "scripts" / "extract_server_command.py"
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value) + "\n", encoding="utf-8", newline="\n")


def _run_extractor(command_json: Path, result: Path) -> subprocess.CompletedProcess[bytes]:
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "src"),
    }
    return subprocess.run(
        [
            str(CMPILOT_PYTHON),
            str(EXTRACTOR),
            "--command-json",
            str(command_json),
            "--result",
            str(result),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=20,
    )


def test_valid_command_array_extracts_without_jq(tmp_path: Path) -> None:
    command = build_qwen32b_server_command(port=47983)
    source = tmp_path / "server-command.json"
    result = tmp_path / "result.json"
    _write_json(source, list(command))

    completed = _run_extractor(source, result)

    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == encode_nul_delimited(command)
    assert b"jq" not in completed.stderr
    assert json.loads(result.read_text())["label"] == "SERVER_COMMAND_EXTRACTION_PASS"


def test_arguments_with_spaces_and_quoted_text_remain_single_elements(
    tmp_path: Path,
) -> None:
    values = [
        "/absolute/python",
        "/model cache/path with spaces",
        'Reply with "READY" exactly',
        "dollar-$-and-single-'quote",
    ]
    source = tmp_path / "command with spaces.json"
    _write_json(source, values)

    loaded = load_command_argv(source)

    assert loaded == tuple(values)
    assert encode_nul_delimited(loaded).split(b"\0")[:-1] == [
        value.encode("utf-8") for value in values
    ]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "non-empty"),
        ({}, "missing"),
        ("not-a-list", "list"),
        (["/absolute/python", 7], "strings"),
        (["/absolute/python", "bad\u0000argument"], "null byte"),
        (["", "-m", "module"], "first argument"),
    ],
)
def test_invalid_command_json_is_rejected_before_indexing(
    tmp_path: Path, value: object, message: str
) -> None:
    source = tmp_path / "invalid.json"
    _write_json(source, value)

    with pytest.raises(CommandExtractionError, match=message):
        load_command_argv(source)


def test_malformed_json_preserves_python_error(tmp_path: Path) -> None:
    source = tmp_path / "malformed.json"
    result = tmp_path / "result.json"
    source.write_text('["unterminated"', encoding="utf-8")

    completed = _run_extractor(source, result)

    assert completed.returncode != 0
    assert b"JSONDecodeError" in completed.stderr
    assert json.loads(result.read_text())["label"] == EXTRACTION_FAILURE


def test_nonexistent_executable_is_rejected(tmp_path: Path) -> None:
    command = list(build_qwen32b_server_command(port=47983))
    missing = tmp_path / "missing-python"
    command[0] = str(missing)

    with pytest.raises(CommandExtractionError, match="executable"):
        validate_qwen32b_server_command(command, expected_python=missing)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda command: command.__setitem__(
            command.index(GUIDED_DECODING_BACKEND), "outlines"
        ),
        lambda command: command.extend(["--quantization", "awq"]),
        lambda command: command.extend(["--cpu-offload-gb", "4"]),
        lambda command: command.extend(["--enable-lora"]),
        lambda command: command.extend(["--speculative-model", "other"]),
    ],
)
def test_prohibited_command_values_are_rejected(mutation) -> None:
    command = list(build_qwen32b_server_command(port=47983))
    mutation(command)

    with pytest.raises(CommandExtractionError):
        validate_qwen32b_server_command(command)


def test_exact_job_25335_legacy_record_is_valid_before_shell_extraction() -> None:
    command = load_command_argv(FIXTURES / "job_25335_server_command.json")

    assert validate_qwen32b_server_command(command) == command
    assert command.count(BACKEND_OPTION) == 1
    assert command[command.index(BACKEND_OPTION) + 1] == GUIDED_DECODING_BACKEND


def test_job_25335_fixture_has_dependency_failure_classification() -> None:
    stderr = (FIXTURES / "job_25335_slurm.stderr").read_text(encoding="utf-8")
    script = (FIXTURES / "job_25335_submitted_excerpt.sbatch").read_text(
        encoding="utf-8"
    )

    result = classify_job_25335_extraction_failure(stderr=stderr, script=script)

    assert result["label"] == EXTRACTION_DEPENDENCY_FAILURE
    assert result["vllm_started"] is False
    assert result["dimensions"] == {
        "gpu_failure": False,
        "guided_backend_failure": False,
        "model_load_failure": False,
        "model_oom": False,
        "tensor_parallel_failure": False,
        "vllm_failure": False,
    }


def test_generated_plan_uses_canonical_top_level_command_array(tmp_path: Path) -> None:
    plan = write_qwen32b_load_gate_plan(tmp_path, port=47983)

    command = json.loads(plan.command_json.read_text(encoding="utf-8"))
    manifest = json.loads(plan.run_manifest.read_text(encoding="utf-8"))

    assert isinstance(command, list)
    assert command == list(build_qwen32b_server_command(port=47983))
    assert manifest["server_command_schema"] == COMMAND_ARRAY_SCHEMA


def test_bash_extraction_rejects_empty_array_without_unbound_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "empty.json"
    artifact_dir = tmp_path / "artifacts"
    _write_json(source, [])
    artifact_dir.mkdir()
    block = render_bash_command_extraction(
        command_json=source,
        artifact_dir=artifact_dir,
        extractor=EXTRACTOR,
    )

    completed = subprocess.run(
        ["/usr/bin/bash", "-c", "set -euo pipefail\n" + block],
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode != 0
    assert "unbound variable" not in completed.stderr
    classification = json.loads(
        (artifact_dir / "server-command-extraction-classification.json").read_text()
    )
    assert classification["label"] == EXTRACTION_FAILURE


def test_bash_extraction_preserves_array_in_noninteractive_minimal_path_shell(
    tmp_path: Path,
) -> None:
    source = tmp_path / "server command.json"
    artifact_dir = tmp_path / "artifact directory"
    artifact_dir.mkdir()
    command = build_qwen32b_server_command(port=47983)
    _write_json(source, list(command))
    block = render_bash_command_extraction(
        command_json=source,
        artifact_dir=artifact_dir,
        extractor=EXTRACTOR,
    )
    shell = block + '\nprintf \'%s\\0\' "${SERVER_CMD[@]}"'

    completed = subprocess.run(
        ["/usr/bin/bash", "-c", "set -euo pipefail\n" + shell],
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == encode_nul_delimited(command)


def test_generated_extraction_block_has_no_jq_eval_or_unsafe_word_splitting(
    tmp_path: Path,
) -> None:
    block = render_bash_command_extraction(
        command_json=tmp_path / "command.json",
        artifact_dir=tmp_path / "artifacts",
        extractor=EXTRACTOR,
    )

    assert "jq" not in block
    assert "eval" not in block
    assert "mapfile -d '' -t SERVER_CMD" in block
    assert "set +e" in block and "set -e" in block
    assert '${SERVER_CMD[0]-}' in block


def test_external_executable_audit_declares_no_jq_dependency() -> None:
    audit = audit_external_executables(scope="cpu", inside_job=False)

    assert audit["pass"] is True
    assert audit["jq_required"] is False
    assert all("jq" not in row["path"] for row in audit["dependencies"])
    assert {row["category"] for row in audit["dependencies"]} == {
        "cluster-core",
        "optional-diagnostic",
        "project-environment",
    }
