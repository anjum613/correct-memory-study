from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


LAUNCHER = Path(__file__).parents[1] / "scripts" / "start_vllm_smoke.sh"


def launcher_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured_args = tmp_path / "singularity-args.txt"
    image = tmp_path / "vllm.sif"
    image.touch()

    singularity = fake_bin / "singularity"
    singularity.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$CAPTURED_ARGS"\n')
    singularity.chmod(0o755)

    ss = fake_bin / "ss"
    ss.write_text("#!/usr/bin/env bash\nexit 0\n")
    ss.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "CAPTURED_ARGS": str(captured_args),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "VLLM_LOG_DIR": str(tmp_path / "logs"),
            "VLLM_SINGULARITY_IMAGE": str(image),
        }
    )
    environment.pop("VLLM_DTYPE", None)
    return environment, captured_args


@pytest.mark.parametrize(
    ("configured_dtype", "expected_dtype"),
    [(None, "half"), ("float16", "float16")],
)
def test_launcher_passes_one_explicit_dtype_argument(
    tmp_path: Path,
    configured_dtype: str | None,
    expected_dtype: str,
) -> None:
    environment, captured_args = launcher_environment(tmp_path)
    if configured_dtype is not None:
        environment["VLLM_DTYPE"] = configured_dtype

    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    arguments = captured_args.read_text().splitlines()
    dtype_positions = [index for index, argument in enumerate(arguments) if argument == "--dtype"]
    assert dtype_positions == [arguments.index("--dtype")]
    assert arguments[dtype_positions[0] + 1] == expected_dtype
    assert f"Selected vLLM dtype: {expected_dtype}" in result.stdout

    backend_positions = [
        index
        for index, argument in enumerate(arguments)
        if argument == "--guided-decoding-backend"
    ]
    assert backend_positions == [arguments.index("--guided-decoding-backend")]
    assert arguments[backend_positions[0] + 1] == "lm-format-enforcer"
    assert "outlines" not in arguments
    assert "Selected guided-decoding backend: lm-format-enforcer" in result.stdout


def test_launcher_help_documents_half_for_turing_quadro_rtx_5000() -> None:
    result = subprocess.run(
        ["bash", str(LAUNCHER), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "VLLM_DTYPE" in result.stdout
    assert "default: half" in result.stdout
    assert "Turing-generation Quadro RTX 5000 GPUs do not support bfloat16" in result.stdout
    assert "VLLM_DTYPE:-bfloat16" not in LAUNCHER.read_text()
