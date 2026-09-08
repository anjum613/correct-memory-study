from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import uuid

import pytest

from cmpilot.working_copy_cpu_job import (
    CPU_GATE_SCRIPT_GENERATION_FAILURE,
    GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE,
    GeneratedScriptArgumentError,
    analyze_generated_script,
    build_working_copy_driver_arguments,
    classify_cpu_gate_script_failure,
    render_shell_argv,
    stage_working_copy_cpu_gate,
    validate_generated_script,
    validate_working_copy_driver_arguments,
)
from scripts.working_copy_cpu_gate import build_parser


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
HPC_SHARED_ROOT = Path("/home/s224049759")
EXPECTED_FINGERPRINT = "6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071"
EXPECTED_RUNTIME_DIGEST = "5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee"
EXPECTED_CACHE_DIGEST = "dd0c2e60a213d49471d16e54ffc7a9eef89bbad87a01d56adf37a901419e9075"


@pytest.fixture
def shared_test_root() -> Path:
    if not HPC_SHARED_ROOT.is_dir():
        pytest.skip("HPC shared home is not present")
    directory = (
        HPC_SHARED_ROOT
        / "run-artifacts"
        / "working-copy-permissions"
        / f"pytest-script-{uuid.uuid4().hex}"
    )
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def _arguments(*, project_root: Path = ROOT) -> tuple[str, ...]:
    return build_working_copy_driver_arguments(
        project_root=project_root,
        source_fixture=project_root / "tasks/smoke_test/repository",
        model_cache_root=Path("/home/s224049759/model-cache/huggingface"),
        cmpilot_python=Path(
            "/home/s224049759/environments/cmpilot-conda/bin/python"
        ),
        vllm_python=Path("/home/s224049759/environments/vllm-smoke/bin/python"),
        expected_environment_fingerprint=EXPECTED_FINGERPRINT,
        expected_runtime_content_digest=EXPECTED_RUNTIME_DIGEST,
        expected_model_cache_digest=EXPECTED_CACHE_DIGEST,
    )


def test_job_25517_fixture_reproduces_five_stray_plus_arguments() -> None:
    script = (FIXTURES / "job_25517_submitted_excerpt.sbatch").read_text(
        encoding="utf-8"
    )

    report = analyze_generated_script(script)

    verifier = report["standalone_plus_by_line"][0]
    assert verifier["count"] == 5
    assert "runtime-input-verification.json" in verifier["text"]
    assert report["standalone_plus_count"] > 5


def test_job_25517_fixture_is_script_generation_failure() -> None:
    script = (FIXTURES / "job_25517_submitted_excerpt.sbatch").read_text(
        encoding="utf-8"
    )
    stderr = (
        "usage: runtime-input-verifier.py [-h]\n"
        "runtime-input-verifier.py: error: unrecognized arguments: + + + + +\n"
    )

    assert (
        classify_cpu_gate_script_failure(stderr=stderr, script=script)
        == CPU_GATE_SCRIPT_GENERATION_FAILURE
    )


def test_structural_shell_rendering_preserves_spaces_quotes_hashes_and_newlines() -> None:
    values = (
        "/absolute/python",
        "/shared/path with spaces/driver.py",
        "quoted 'value'",
        EXPECTED_CACHE_DIGEST,
        "line one\nline two",
    )

    rendered = render_shell_argv(values)

    assert tuple(shlex.split(rendered, posix=True)) == values


def test_literal_plus_requires_explicit_schema_permission() -> None:
    with pytest.raises(GeneratedScriptArgumentError, match="standalone plus"):
        render_shell_argv(("python", "+"))

    rendered = render_shell_argv(
        ("python", "+"), allowed_literal_plus_indices=frozenset({1})
    )
    assert shlex.split(rendered) == ["python", "+"]


def test_driver_parser_accepts_exact_structured_arguments() -> None:
    arguments = _arguments()

    parsed = validate_working_copy_driver_arguments(
        arguments, parser=build_parser()
    )

    assert parsed["argument_count"] == len(arguments)
    assert parsed["arguments"] == list(arguments)
    assert parsed["expected_environment_fingerprint"] == EXPECTED_FINGERPRINT
    assert parsed["expected_runtime_content_digest"] == EXPECTED_RUNTIME_DIGEST
    assert parsed["expected_model_cache_digest"] == EXPECTED_CACHE_DIGEST


@pytest.mark.parametrize(
    "arguments",
    [
        lambda values: values[:-2],
        lambda values: (*values, "--unexpected", "value"),
    ],
)
def test_missing_or_extra_driver_arguments_fail_before_submission(arguments) -> None:
    with pytest.raises(
        GeneratedScriptArgumentError,
        match=GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE,
    ):
        validate_working_copy_driver_arguments(
            arguments(_arguments()), parser=build_parser()
        )


def test_generated_cpu_gate_has_exact_arguments_and_no_stray_plus(
    shared_test_root: Path,
) -> None:
    bundle = stage_working_copy_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "pre-submit",
        source_fixture=ROOT / "tasks/smoke_test/repository",
        model_cache_root=Path("/home/s224049759/model-cache/huggingface"),
        expected_environment_fingerprint=EXPECTED_FINGERPRINT,
        expected_runtime_content_digest=EXPECTED_RUNTIME_DIGEST,
        expected_model_cache_digest=EXPECTED_CACHE_DIGEST,
        artifact_root=shared_test_root / "artifacts",
    )
    script = bundle.submitted_script.read_text(encoding="utf-8")

    report = validate_generated_script(
        bundle.submitted_script,
        expected_driver_arguments=bundle.driver_arguments,
        parser=build_parser(),
    )

    assert report["standalone_plus_count"] == 0
    assert report["patch_marker_count"] == 0
    assert report["driver_argument_count"] == len(bundle.driver_arguments)
    assert tuple(report["driver_arguments"]) == bundle.driver_arguments
    assert "/usr/bin/jq" not in script
    assert "/tmp/" not in script
    assert "#SBATCH --partition=Virtual" in script
    assert "#SBATCH --cpus-per-task=2" in script
    assert "#SBATCH --mem=4G" in script
    assert "#SBATCH --time=00:20:00" in script


def test_generated_script_passes_bash_syntax_and_actual_argparse(
    shared_test_root: Path,
) -> None:
    bundle = stage_working_copy_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "syntax-pre-submit",
        source_fixture=ROOT / "tasks/smoke_test/repository",
        model_cache_root=Path("/home/s224049759/model-cache/huggingface"),
        expected_environment_fingerprint=EXPECTED_FINGERPRINT,
        expected_runtime_content_digest=EXPECTED_RUNTIME_DIGEST,
        expected_model_cache_digest=EXPECTED_CACHE_DIGEST,
        artifact_root=shared_test_root / "syntax-artifacts",
    )

    completed = subprocess.run(
        ["/usr/bin/bash", "-n", str(bundle.submitted_script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    parsed = build_parser().parse_args(bundle.driver_arguments)

    assert completed.returncode == 0, completed.stderr
    assert parsed.source_fixture == ROOT / "tasks/smoke_test/repository"


def test_generated_manifest_records_argument_inventory(
    shared_test_root: Path,
) -> None:
    bundle = stage_working_copy_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "manifest-pre-submit",
        source_fixture=ROOT / "tasks/smoke_test/repository",
        model_cache_root=Path("/home/s224049759/model-cache/huggingface"),
        expected_environment_fingerprint=EXPECTED_FINGERPRINT,
        expected_runtime_content_digest=EXPECTED_RUNTIME_DIGEST,
        expected_model_cache_digest=EXPECTED_CACHE_DIGEST,
        artifact_root=shared_test_root / "manifest-artifacts",
    )

    manifest = json.loads(bundle.runtime_manifest.read_text(encoding="utf-8"))

    assert manifest["schema"] == "working-copy-cpu-gate-bundle-v1"
    assert manifest["driver_invocation"]["argument_count"] == len(
        bundle.driver_arguments
    )
    assert manifest["script_validation"]["standalone_plus_count"] == 0
    assert manifest["script_validation"]["bash_syntax"] == "PASS"
