from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from cmpilot.batch_script_attestation import (
    ATTESTATION_FAILURE,
    ATTESTATION_PASS,
    CAUSE_UNCONFIRMED,
    AttestationError,
    attest_batch_script_files,
    classify_job_25371_attestation,
    compare_digest_values,
    observe_running_script,
    require_digest_match,
    retrieve_controller_batch_script,
    submit_with_controller_attestation,
)
from cmpilot.file_digest import FileDigestError, sha256_file
from cmpilot.shared_runtime import (
    StagedRuntimeDriver,
    render_cpu_gate_wrapper,
    stage_runtime_driver,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
HPC_SHARED_ROOT = Path("/home/s224049759")
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
DIGEST_TOOL = ROOT / "scripts" / "batch_script_attestation.py"


@pytest.fixture
def shared_test_root() -> Path:
    if not HPC_SHARED_ROOT.is_dir():
        pytest.skip("HPC shared home is not present")
    directory = (
        HPC_SHARED_ROOT
        / "run-artifacts"
        / "batch-script-attestation"
        / f"pytest-{uuid.uuid4().hex}"
    )
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def _executable(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8", newline="\n")
    path.chmod(0o700)
    return path


def _fake_slurm_commands(
    tmp_path: Path, source_script: Path, *, retrieval_exit: int = 0
) -> tuple[Path, Path, Path, Path, Path]:
    submit_count = tmp_path / "submit-count.txt"
    cancel_count = tmp_path / "cancel-count.txt"
    sbatch = _executable(
        tmp_path / "sbatch",
        "#!/usr/bin/python3\n"
        "from pathlib import Path\n"
        f"p=Path({str(submit_count)!r})\n"
        "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
        "print('70001')\n",
    )
    if retrieval_exit == 0:
        scontrol_body = (
            "#!/usr/bin/python3\n"
            "from pathlib import Path\n"
            "import shutil,sys\n"
            f"shutil.copyfile({str(source_script)!r}, sys.argv[-1])\n"
            "print('controller copy written')\n"
        )
    else:
        scontrol_body = (
            "#!/usr/bin/python3\n"
            "import sys\n"
            "print('controller retrieval failed', file=sys.stderr)\n"
            f"raise SystemExit({retrieval_exit})\n"
        )
    scontrol = _executable(tmp_path / "scontrol", scontrol_body)
    scancel = _executable(
        tmp_path / "scancel",
        "#!/usr/bin/python3\n"
        "from pathlib import Path\n"
        f"p=Path({str(cancel_count)!r})\n"
        "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n",
    )
    return sbatch, scontrol, scancel, submit_count, cancel_count


def test_identical_source_and_controller_bytes_pass(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    controller = tmp_path / "controller.sbatch"
    source.write_bytes(b"#!/bin/bash\ntrue\n")
    controller.write_bytes(source.read_bytes())

    result = attest_batch_script_files(
        source, controller, evidence_dir=tmp_path / "evidence"
    )

    assert result["label"] == ATTESTATION_PASS
    assert result["pass"] is True
    assert result["source_digest"] == result["controller_digest"]
    assert len(result["source_digest"]) == 64
    assert (tmp_path / "evidence/source-digest.raw").read_bytes() == result[
        "source_digest"
    ].encode("ascii")


def test_one_byte_script_difference_fails_and_reports_offset(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    controller = tmp_path / "controller.sbatch"
    source.write_bytes(b"#!/bin/bash\ntrue\n")
    controller.write_bytes(b"#!/bin/bash\nfalse\n")

    result = attest_batch_script_files(source, controller)

    assert result["label"] == ATTESTATION_FAILURE
    assert result["pass"] is False
    assert result["file_first_difference"]["byte_index"] == 12


def test_missing_controller_copy_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    source.write_bytes(b"#!/bin/bash\n")

    result = attest_batch_script_files(source, tmp_path / "missing.sbatch")

    assert result["label"] == ATTESTATION_FAILURE
    assert "does not exist" in result["controller_error"]


def test_failed_controller_retrieval_preserves_process_evidence(tmp_path: Path) -> None:
    failing = _executable(
        tmp_path / "scontrol",
        "#!/usr/bin/python3\n"
        "import sys\n"
        "print('retrieval stdout')\n"
        "print('retrieval stderr', file=sys.stderr)\n"
        "raise SystemExit(9)\n",
    )
    evidence = tmp_path / "evidence"

    result = retrieve_controller_batch_script(
        "70001",
        tmp_path / "controller.sbatch",
        evidence_dir=evidence,
        scontrol=failing,
    )

    assert result["exit_code"] == 9
    assert result["pass"] is False
    assert (evidence / "controller-retrieval.stdout").read_text() == "retrieval stdout\n"
    assert (evidence / "controller-retrieval.stderr").read_text() == "retrieval stderr\n"
    assert (evidence / "controller-retrieval.exit").read_text() == "9\n"


def test_plain_digest_and_sha256sum_output_do_not_silently_compare() -> None:
    digest = "a" * 64
    result = compare_digest_values(
        digest, f"{digest}  /shared/script.sbatch\n", context="batch-script"
    )

    assert result["pass"] is False
    assert result["observed"]["valid_plain_digest"] is False
    assert result["first_character_difference"]["index"] == 64


@pytest.mark.parametrize("observed", [" " + "a" * 64, "a" * 64 + "\n"])
def test_digest_whitespace_is_detected(observed: str) -> None:
    result = compare_digest_values("a" * 64, observed, context="whitespace")

    assert result["pass"] is False
    assert result["observed"]["normalization_changed"] is True


def test_crlf_and_lf_script_hashes_differ_without_normalization(tmp_path: Path) -> None:
    lf = tmp_path / "lf.sbatch"
    crlf = tmp_path / "crlf.sbatch"
    lf.write_bytes(b"#!/bin/bash\ntrue\n")
    crlf.write_bytes(b"#!/bin/bash\r\ntrue\r\n")

    result = attest_batch_script_files(lf, crlf)

    assert sha256_file(lf) != sha256_file(crlf)
    assert result["pass"] is False
    assert result["file_first_difference"]["byte_index"] == 11


@pytest.mark.parametrize(
    ("expected", "observed", "invalid_side"),
    [("", "a" * 64, "expected"), ("a" * 64, "", "observed")],
)
def test_empty_digest_fails_clearly(
    expected: str, observed: str, invalid_side: str
) -> None:
    result = compare_digest_values(expected, observed, context="empty")

    assert result["pass"] is False
    assert result[invalid_side]["valid_plain_digest"] is False


def test_non_hex_digest_fails_validation() -> None:
    result = compare_digest_values("g" * 64, "g" * 64, context="nonhex")

    assert result["pass"] is False
    assert result["expected"]["valid_plain_digest"] is False


def test_missing_file_digest_is_an_explicit_error(tmp_path: Path) -> None:
    with pytest.raises(FileDigestError, match="does not exist"):
        sha256_file(tmp_path / "missing")


def test_job_25371_is_implementation_failure_not_script_mutation() -> None:
    fixture = json.loads(
        (FIXTURES / "job_25371_attestation.json").read_text(encoding="utf-8")
    )
    excerpt = (FIXTURES / "job_25371_submitted_excerpt.sbatch").read_text(
        encoding="utf-8"
    )

    result = classify_job_25371_attestation(fixture=fixture, script=excerpt)

    assert result["label"] == CAUSE_UNCONFIRMED
    assert result["root_cause_category"] == "BATCH_SCRIPT_ATTESTATION_IMPLEMENTATION_FAILURE"
    assert result["script_mutation"] is False
    assert result["exact_comparison_cause_confirmed"] is False


def test_three_matching_copies_establish_controller_attestation(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("source", "submitted", "controller")]
    for path in paths:
        path.write_bytes(b"#!/bin/bash\nexit 0\n")

    result = attest_batch_script_files(paths[0], paths[2])

    assert result["pass"] is True
    assert sha256_file(paths[0]) == sha256_file(paths[1]) == sha256_file(paths[2])


def test_unavailable_running_script_observation_is_nonblocking(tmp_path: Path) -> None:
    record = tmp_path / "observation.json"

    result = observe_running_script("/does/not/exist/slurm-script", record)

    assert result["blocking"] is False
    assert result["inspection_available"] is False
    assert result["hash_exit_status"] != 0
    assert record.is_file()


def test_running_script_observation_preserves_path_and_hash(tmp_path: Path) -> None:
    script = tmp_path / "running.sbatch"
    script.write_bytes(b"#!/bin/bash\n")

    result = observe_running_script(str(script), tmp_path / "observation.json")

    assert result["inspection_available"] is True
    assert result["raw_path"] == str(script)
    assert result["resolved_path"] == str(script.resolve())
    assert result["sha256"] == sha256_file(script)
    assert result["hash_exit_status"] == 0


@pytest.mark.parametrize(
    "context",
    [
        "server-command-plan",
        "environment-fingerprint-v2",
        "runtime-content-digest",
        "model-cache-digest",
    ],
)
def test_named_runtime_integrity_mismatches_fail_closed(
    tmp_path: Path, context: str
) -> None:
    evidence = tmp_path / f"{context}.json"

    with pytest.raises(AttestationError, match=context):
        require_digest_match("a" * 64, "b" * 64, context=context, record=evidence)

    assert json.loads(evidence.read_text())["pass"] is False


def _render_strict_wrapper(
    tmp_path: Path, shared_test_root: Path
) -> tuple[str, Path, Path, Path]:
    source = tmp_path / "driver.sh"
    source.write_text(
        "#!/usr/bin/bash\n"
        "set -euo pipefail\n"
        'printf "RAN\\n" > "${BACKEND_MARKER:?}"\n',
        encoding="utf-8",
        newline="\n",
    )
    staged = stage_runtime_driver(
        source,
        shared_test_root / "pre-submit",
        shared_roots=(shared_test_root,),
        destination_name="driver.sh",
    )
    plan = staged.path.parent / "server-command.json"
    plan.write_text('["python", "-m", "server"]\n', encoding="utf-8", newline="\n")
    plan.chmod(0o444)
    plan_reference = StagedRuntimeDriver(
        path=plan, sha256=sha256_file(plan), source=plan
    )
    wrapper = render_cpu_gate_wrapper(
        driver_path=staged.path,
        driver_sha256=staged.sha256,
        artifact_root=tmp_path / "artifacts",
        driver_interpreter=Path("/usr/bin/bash"),
        strict_runtime_inputs=(plan_reference,),
        digest_tool=DIGEST_TOOL,
        shared_roots=(HPC_SHARED_ROOT,),
    )
    wrapper_path = staged.path.parent / "gate.sbatch"
    wrapper_path.write_text(wrapper, encoding="utf-8", newline="\n")
    return wrapper, wrapper_path, staged.path, plan


def _run_wrapper(wrapper: Path, marker: Path, job_id: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update({"BACKEND_MARKER": str(marker), "SLURM_JOB_ID": job_id})
    return subprocess.run(
        ["/usr/bin/bash", str(wrapper)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_generated_wrapper_has_observational_self_hash_and_no_self_gate(
    tmp_path: Path, shared_test_root: Path
) -> None:
    wrapper, _, _, _ = _render_strict_wrapper(tmp_path, shared_test_root)

    assert 'observe --path "$0"' in wrapper
    assert "SUBMITTED_SCRIPT_SHA256" not in wrapper
    assert "sha256sum" not in wrapper
    assert "jq" not in wrapper
    assert "eval" not in wrapper
    assert "/tmp/" not in "\n".join(
        line for line in wrapper.splitlines() if "CMPILOT_REQUIRED_RUNTIME_FILE" in line
    )


def test_shared_driver_hash_mismatch_still_blocks_execution(
    tmp_path: Path, shared_test_root: Path
) -> None:
    _, wrapper, driver, _ = _render_strict_wrapper(tmp_path, shared_test_root)
    driver.chmod(0o600)
    driver.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8")
    marker = tmp_path / "ran"

    completed = _run_wrapper(wrapper, marker, "80001")

    assert completed.returncode != 0
    assert not marker.exists()
    classification = json.loads(
        (tmp_path / "artifacts/80001/classification.json").read_text()
    )
    assert classification["label"] == "RUNTIME_SOURCE_HASH_MISMATCH"


def test_server_command_plan_hash_mismatch_still_blocks_execution(
    tmp_path: Path, shared_test_root: Path
) -> None:
    _, wrapper, _, plan = _render_strict_wrapper(tmp_path, shared_test_root)
    plan.chmod(0o600)
    plan.write_text('["changed"]\n', encoding="utf-8")
    marker = tmp_path / "ran"

    completed = _run_wrapper(wrapper, marker, "80002")

    assert completed.returncode != 0
    assert not marker.exists()
    artifact_dir = tmp_path / "artifacts/80002"
    classification = json.loads((artifact_dir / "classification.json").read_text())
    comparison = json.loads(
        (artifact_dir / "strict-runtime-input-0-digest-comparison.json").read_text()
    )
    assert classification["label"] == "RUNTIME_SOURCE_HASH_MISMATCH"
    assert comparison["context"] == "server-command-plan"
    assert comparison["pass"] is False


def test_strict_inputs_pass_and_are_copied_with_observation(
    tmp_path: Path, shared_test_root: Path
) -> None:
    _, wrapper, _, plan = _render_strict_wrapper(tmp_path, shared_test_root)
    marker = tmp_path / "ran"

    completed = _run_wrapper(wrapper, marker, "80003")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert marker.read_text() == "RAN\n"
    artifact_dir = tmp_path / "artifacts/80003"
    assert (artifact_dir / "strict-runtime-input-0").read_bytes() == plan.read_bytes()
    observation = json.loads(
        (artifact_dir / "running-script-observation.json").read_text()
    )
    assert observation["blocking"] is False
    assert observation["inspection_available"] is True


def test_submit_once_and_attest_matching_controller_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    source.write_bytes(b"#!/usr/bin/bash\nexit 0\n")
    sbatch, scontrol, scancel, submit_count, cancel_count = _fake_slurm_commands(
        tmp_path, source
    )

    result = submit_with_controller_attestation(
        source,
        evidence_dir=tmp_path / "evidence",
        sbatch=sbatch,
        scontrol=scontrol,
        scancel=scancel,
    )

    assert result["label"] == ATTESTATION_PASS
    assert result["pass"] is True
    assert result["job_id"] == "70001"
    assert submit_count.read_text() == "1"
    assert not cancel_count.exists()
    submission = json.loads((tmp_path / "evidence/submission.json").read_text())
    assert submission["argv"].count(str(source.resolve())) == 1
    assert "--begin=now+2minutes" in submission["argv"]
    assert (tmp_path / "evidence/controller-batch-script.sbatch").read_bytes() == (
        source.read_bytes()
    )


def test_failed_controller_retrieval_cancels_only_submitted_job(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sbatch"
    source.write_bytes(b"#!/usr/bin/bash\nexit 0\n")
    sbatch, scontrol, scancel, submit_count, cancel_count = _fake_slurm_commands(
        tmp_path, source, retrieval_exit=9
    )

    result = submit_with_controller_attestation(
        source,
        evidence_dir=tmp_path / "evidence",
        sbatch=sbatch,
        scontrol=scontrol,
        scancel=scancel,
    )

    assert result["label"] == ATTESTATION_FAILURE
    assert result["pass"] is False
    assert result["cancelled"] is True
    assert submit_count.read_text() == "1"
    assert cancel_count.read_text() == "1"
    assert (tmp_path / "evidence/controller-retrieval.exit").read_text() == "9\n"
    assert (tmp_path / "evidence/controller-retrieval.stderr").read_text() == (
        "controller retrieval failed\n"
    )


def test_controller_byte_mismatch_cancels_the_submitted_job(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    source.write_bytes(b"#!/usr/bin/bash\nexit 0\n")
    sbatch, _, scancel, submit_count, cancel_count = _fake_slurm_commands(
        tmp_path, source
    )
    scontrol = _executable(
        tmp_path / "mutating-scontrol",
        "#!/usr/bin/python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[-1]).write_bytes(b'#!/usr/bin/bash\\nexit 1\\n')\n",
    )

    result = submit_with_controller_attestation(
        source,
        evidence_dir=tmp_path / "evidence",
        sbatch=sbatch,
        scontrol=scontrol,
        scancel=scancel,
    )

    assert result["label"] == ATTESTATION_FAILURE
    assert result["attestation"]["file_first_difference"] is not None
    assert submit_count.read_text() == "1"
    assert cancel_count.read_text() == "1"


def test_attestation_cli_reports_plain_exact_digest(tmp_path: Path) -> None:
    source = tmp_path / "bytes.bin"
    source.write_bytes(b"exact bytes\r\n")

    completed = subprocess.run(
        [
            str(CMPILOT_PYTHON),
            str(DIGEST_TOOL),
            "digest",
            "--path",
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0
    assert completed.stdout.rstrip("\n") == sha256_file(source)
    assert len(completed.stdout.rstrip("\n")) == 64


def test_submission_cli_has_one_submit_path_and_controller_retrieval() -> None:
    source = (ROOT / "scripts/submit_attested_batch.py").read_text(encoding="utf-8")

    assert "submit_with_controller_attestation" in source
    assert "sacct --batch-script" not in source
    assert "scontrol write batch_script" not in source
    assert "sha256sum" not in source
    assert "SUBMITTED_SCRIPT_SHA256" not in source


def test_missing_submission_dependency_blocks_before_sbatch(tmp_path: Path) -> None:
    source = tmp_path / "source.sbatch"
    source.write_bytes(b"#!/usr/bin/bash\nexit 0\n")
    sbatch, _, scancel, submit_count, _ = _fake_slurm_commands(tmp_path, source)

    result = submit_with_controller_attestation(
        source,
        evidence_dir=tmp_path / "evidence",
        sbatch=sbatch,
        scontrol=tmp_path / "missing-scontrol",
        scancel=scancel,
    )

    assert result["pass"] is False
    assert result["submission_once"] is False
    assert result["job_id"] is None
    assert not submit_count.exists()
    audit = json.loads(
        (tmp_path / "evidence/submission-executable-audit.json").read_text()
    )
    assert audit["pass"] is False


def test_cluster_submission_executable_defaults_are_absolute_and_present() -> None:
    for executable in ("sbatch", "scontrol", "scancel"):
        path = Path("/slurm/bin") / executable
        assert path.is_absolute()
        assert path.is_file() and os.access(path, os.X_OK)
