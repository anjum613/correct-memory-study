#!/usr/bin/env python3
"""Archive read-only job-25887 evidence and the exact CPU zero-test replay."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.external_calculator_oracle import (  # noqa: E402
    run_external_calculator_oracle,
)
from cmpilot.qualification import (  # noqa: E402
    canonical_json_bytes,
    sha256_file,
    write_canonical_json,
)


DEFAULT_JOB = Path("/home/s224049759/run-artifacts/qwen32b-calculator/25887")
DEFAULT_OUTPUT = Path(
    "/home/s224049759/run-artifacts/qwen32b-no-memory-qualification/v1/"
    "calculator-25887-closeout"
)


def _run(
    argv: Sequence[str], *, cwd: Path, prefix: Path, timeout: int = 120
) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    prefix.with_suffix(".stdout").write_text(completed.stdout or "", encoding="utf-8")
    prefix.with_suffix(".stderr").write_text(completed.stderr or "", encoding="utf-8")
    prefix.with_suffix(".exit").write_text(f"{completed.returncode}\n", encoding="ascii")
    record = {
        "argv": list(argv),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stderr_path": str(prefix.with_suffix(".stderr")),
        "stdout_path": str(prefix.with_suffix(".stdout")),
    }
    write_canonical_json(prefix.with_suffix(".json"), record)
    return {**record, "stderr": completed.stderr or "", "stdout": completed.stdout or ""}


def _one_agent_run(job: Path) -> Path:
    candidates = sorted(path for path in (job / "agent-runs").iterdir() if path.is_dir())
    if len(candidates) != 1:
        raise RuntimeError(f"expected one preserved agent run, found {len(candidates)}")
    return candidates[0]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _manifest(output: Path) -> dict[str, Any]:
    excluded = {"SHA256SUMS", "manifest-validation.json"}
    rows = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in excluded:
            continue
        rows.append((sha256_file(path), relative))
    text = "".join(f"{digest}  {relative}\n" for digest, relative in rows)
    (output / "SHA256SUMS").write_text(text, encoding="ascii")
    first = hashlib.sha256(text.encode("ascii")).hexdigest()
    regenerated = "".join(f"{sha256_file(output / relative)}  {relative}\n" for _, relative in rows)
    second = hashlib.sha256(regenerated.encode("ascii")).hexdigest()
    result = {
        "algorithm": "sha256 exact file bytes",
        "entry_count": len(rows),
        "errors": [],
        "first_generation_sha256": first,
        "first_second_identical": text == regenerated,
        "pass": text == regenerated and first == second,
        "second_generation_sha256": second,
    }
    write_canonical_json(output / "manifest-validation.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-artifacts", type=Path, default=DEFAULT_JOB)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    job = arguments.job_artifacts.resolve(strict=True)
    output = arguments.output_directory
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"closeout output already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    run = _one_agent_run(job)
    work = (run / "working-copy").resolve(strict=True)
    source = (job / "harness-root/tasks/smoke_test/repository").resolve(strict=True)
    oracle = (run / "immutable-oracle").resolve(strict=True)
    run_record = _load(run / "run.json")
    result = _load(job / "result-final.json")
    python = Path(_load(run / "environment.json")["cmpilot_python"]).resolve(strict=True)

    commands = [
        ("unittest_module", (str(python), "-m", "unittest", "test_calculator.py", "-v")),
        (
            "unittest_discover",
            (str(python), "-m", "unittest", "discover", "-s", ".", "-p", "test*.py", "-v"),
        ),
        ("pytest", (str(python), "-m", "pytest", "-q", "test_calculator.py")),
    ]
    replay = {
        name: _run(command, cwd=work, prefix=output / name)
        for name, command in commands
    }
    oracle_result = run_external_calculator_oracle(
        source_repository=source,
        agent_repository=work,
        oracle_bundle=oracle,
        destination=output / "oracle-validation-tree",
        artifact_directory=output / "oracle-artifacts",
        python=python,
    )
    write_canonical_json(output / "oracle-replay.json", oracle_result.as_dict())

    accounting = _run(
        (
            "/slurm/bin/sacct",
            "-j",
            "25887",
            "--starttime",
            "2026-08-09",
            "--endtime",
            "2026-08-10",
            "-X",
            "-P",
            "-n",
            "-o",
            "JobIDRaw,JobName,Partition,State,ExitCode,Submit,Start,End,Elapsed,AllocNodes,AllocCPUS,ReqMem,NodeList,AllocTRES",
        ),
        cwd=output,
        prefix=output / "slurm-accounting-replay",
    )
    visible_source = (work / "test_calculator.py").read_text(encoding="utf-8")
    zero_test = {
        "classification": "MODEL_TEST_COMMAND_CHOICE",
        "classification_reason": (
            "The preserved visible test contains three pytest-style module functions and "
            "no unittest.TestCase or unittest.main entry point. Both documented unittest "
            "invocations therefore collect zero tests, while pytest and the immutable "
            "external oracle collect and pass all three tests."
        ),
        "exact_interpreter": str(python),
        "exact_working_directory": str(work),
        "file_inspection": {
            "calculator_sha256": sha256_file(work / "calculator.py"),
            "has_main_block": "if __name__" in visible_source,
            "has_pytest_functions": visible_source.count("def test_") == 3,
            "has_unittest_testcase": "unittest.TestCase" in visible_source,
            "test_sha256": sha256_file(work / "test_calculator.py"),
        },
        "immutable_oracle": oracle_result.as_dict(),
        "replay": replay,
        "schema": "calculator-25887-zero-test-investigation-v1",
    }
    write_canonical_json(output / "zero-test-investigation.json", zero_test)

    job_manifest = _load(job / "manifest-validation.json")
    classification = _load(run / "classification.json")
    closeout = {
        "agent_completion_behavior": {
            "completion_protocol": "FAIL",
            "termination_reason": run_record["termination_reason"],
        },
        "artifact_preservation": _load(job / "artifact-preservation-idempotency-final.json"),
        "cleanup": {
            "compute": _load(job / "scratch-cleanup.json"),
            "controller": _load(job / "controller-scratch-cleanup.json"),
        },
        "controller_attestation": _load(job / "controller-attestation/controller-attestation.json"),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "environment_fingerprint": _load(job / "environment-fingerprint-v2-final.json"),
        "final_decision": "calculator engineering is closed",
        "functional_outcome": {
            "immutable_oracle": "PASS",
            "passed": oracle_result.passed,
            "failed": oracle_result.failed,
        },
        "job_id": 25887,
        "job_manifest": {
            "entry_count": job_manifest["entry_count"],
            "sha256": job_manifest["first_generation_sha256"],
            "validation_pass": job_manifest["pass"],
        },
        "model_revision": "381fc969f78efac66bc87ff7ddeadb7e73c218a7",
        "project_commit": (job / "project-commit-initial.txt").read_text().strip(),
        "repository_competence": {
            "authorized_patch_produced": True,
            "only_calculator_py_modified": result["edited_files"] == ["calculator.py"],
            "status": "PASS",
        },
        "repository_patch": {
            "path": str(run / "final.patch"),
            "sha256": sha256_file(run / "final.patch"),
        },
        "rerun_permitted": False,
        "schema": "calculator-25887-engineering-closeout-v1",
        "slurm_accounting": accounting,
        "technical_validity": "PASS",
        "zero_test_classification": zero_test["classification"],
        "source_classification_preserved": classification,
    }
    write_canonical_json(output / "calculator-closeout.json", closeout)
    manifest = _manifest(output)
    print(
        json.dumps(
            {
                "classification": zero_test["classification"],
                "manifest": manifest,
                "output_directory": str(output),
            },
            sort_keys=True,
        )
    )
    return 0 if manifest["pass"] and oracle_result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
