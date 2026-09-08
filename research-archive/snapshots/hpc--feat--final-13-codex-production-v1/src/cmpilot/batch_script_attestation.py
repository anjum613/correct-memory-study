"""Controller-side Slurm batch-script attestation and digest evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence

from cmpilot.file_digest import FileDigestError, SHA256_HEX_PATTERN, sha256_file


ATTESTATION_PASS = "CONTROLLER_BATCH_SCRIPT_ATTESTATION_PASS"
ATTESTATION_FAILURE = "CONTROLLER_BATCH_SCRIPT_ATTESTATION_FAILURE"
CAUSE_UNCONFIRMED = "BATCH_SCRIPT_ATTESTATION_COMPARISON_CAUSE_UNCONFIRMED"
RUNTIME_INPUT_FAILURE = "RUNTIME_SOURCE_HASH_MISMATCH"


class AttestationError(RuntimeError):
    """A strict runtime-input digest comparison failed."""


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _value_evidence(value: str) -> dict[str, object]:
    raw_bytes = value.encode("utf-8")
    normalized = value.strip()
    return {
        "escaped_text": ascii(value),
        "length_bytes": len(raw_bytes),
        "length_characters": len(value),
        "normalization_changed": normalized != value,
        "normalized": normalized,
        "normalized_length": len(normalized),
        "raw": value,
        "raw_bytes_hex": raw_bytes.hex(),
        "valid_normalized_digest": bool(SHA256_HEX_PATTERN.fullmatch(normalized)),
        "valid_plain_digest": bool(SHA256_HEX_PATTERN.fullmatch(value)),
    }


def _first_character_difference(left: str, right: str) -> dict[str, object] | None:
    for index, (left_character, right_character) in enumerate(zip(left, right)):
        if left_character != right_character:
            return {
                "expected": ascii(left_character),
                "index": index,
                "observed": ascii(right_character),
            }
    if len(left) == len(right):
        return None
    index = min(len(left), len(right))
    return {
        "expected": "<end>" if index == len(left) else ascii(left[index]),
        "index": index,
        "observed": "<end>" if index == len(right) else ascii(right[index]),
    }


def _first_byte_difference(left: bytes, right: bytes) -> dict[str, object] | None:
    for index, (left_byte, right_byte) in enumerate(zip(left, right)):
        if left_byte != right_byte:
            return {
                "byte_index": index,
                "expected": left_byte,
                "observed": right_byte,
            }
    if len(left) == len(right):
        return None
    index = min(len(left), len(right))
    return {
        "byte_index": index,
        "expected": None if index == len(left) else left[index],
        "observed": None if index == len(right) else right[index],
    }


def compare_digest_values(
    expected: str, observed: str, *, context: str
) -> dict[str, object]:
    """Compare plain digest representations without silently normalizing them."""
    expected_evidence = _value_evidence(expected)
    observed_evidence = _value_evidence(observed)
    passed = bool(
        expected_evidence["valid_plain_digest"]
        and observed_evidence["valid_plain_digest"]
        and expected == observed
    )
    return {
        "context": context,
        "expected": expected_evidence,
        "first_byte_difference": _first_byte_difference(
            expected.encode("utf-8"), observed.encode("utf-8")
        ),
        "first_character_difference": _first_character_difference(expected, observed),
        "observed": observed_evidence,
        "pass": passed,
        "schema": "canonical-sha256-comparison-v1",
    }


def require_digest_match(
    expected: str,
    observed: str,
    *,
    context: str,
    record: Path | None = None,
) -> dict[str, object]:
    """Fail closed for a strict runtime input while retaining comparison evidence."""
    result = compare_digest_values(expected, observed, context=context)
    result["label"] = "PASS" if result["pass"] else RUNTIME_INPUT_FAILURE
    if record is not None:
        _write_json(record, result)
    if not result["pass"]:
        raise AttestationError(f"{context}: {RUNTIME_INPUT_FAILURE}")
    return result


def attest_batch_script_files(
    source_script: Path,
    controller_script: Path,
    *,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    """Attest exact source bytes against the Slurm controller-stored copy."""
    source_script = Path(source_script)
    controller_script = Path(controller_script)
    result: dict[str, Any] = {
        "controller_path": str(controller_script),
        "label": ATTESTATION_FAILURE,
        "pass": False,
        "schema": "slurm-controller-batch-script-attestation-v1",
        "source_path": str(source_script),
    }
    try:
        source_digest = sha256_file(source_script)
        result["source_digest"] = source_digest
    except FileDigestError as error:
        result["source_error"] = str(error)
        source_digest = None
    try:
        controller_digest = sha256_file(controller_script)
        result["controller_digest"] = controller_digest
    except FileDigestError as error:
        result["controller_error"] = str(error)
        controller_digest = None

    if source_digest is not None and controller_digest is not None:
        comparison = compare_digest_values(
            source_digest, controller_digest, context="controller-batch-script"
        )
        result["digest_comparison"] = comparison
        source_bytes = source_script.read_bytes()
        controller_bytes = controller_script.read_bytes()
        result["file_first_difference"] = _first_byte_difference(
            source_bytes, controller_bytes
        )
        result["source_size"] = len(source_bytes)
        result["controller_size"] = len(controller_bytes)
        result["pass"] = comparison["pass"] and source_bytes == controller_bytes
        result["label"] = ATTESTATION_PASS if result["pass"] else ATTESTATION_FAILURE

    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        if source_digest is not None:
            (evidence_dir / "source-digest.raw").write_bytes(
                source_digest.encode("ascii")
            )
        if controller_digest is not None:
            (evidence_dir / "controller-digest.raw").write_bytes(
                controller_digest.encode("ascii")
            )
        _write_json(evidence_dir / "controller-attestation.json", result)
    return result


def _run_process(argv: Sequence[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            list(argv), check=False, capture_output=True, timeout=60
        )
        return {
            "argv": list(argv),
            "exit_code": completed.returncode,
            "stderr": completed.stderr,
            "stdout": completed.stdout,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(argv),
            "error": f"{type(error).__name__}: {error}",
            "exit_code": 124 if isinstance(error, subprocess.TimeoutExpired) else 127,
            "stderr": str(error).encode("utf-8"),
            "stdout": b"",
        }


def _preserve_process(prefix: Path, process: dict[str, object]) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".stdout").write_bytes(process["stdout"])
    prefix.with_suffix(".stderr").write_bytes(process["stderr"])
    prefix.with_suffix(".exit").write_text(
        f"{process['exit_code']}\n", encoding="ascii", newline="\n"
    )
    _write_json(
        prefix.with_suffix(".json"),
        {
            key: value
            for key, value in process.items()
            if key not in {"stdout", "stderr"}
        },
    )


def retrieve_controller_batch_script(
    job_id: str,
    output_path: Path,
    *,
    evidence_dir: Path,
    scontrol: Path = Path("/slurm/bin/scontrol"),
) -> dict[str, object]:
    """Retrieve the controller copy with ``scontrol write batch_script``."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = _run_process(
        (str(scontrol), "write", "batch_script", str(job_id), str(output_path))
    )
    _preserve_process(evidence_dir / "controller-retrieval", process)
    passed = process["exit_code"] == 0 and output_path.is_file()
    result = {
        "argv": process["argv"],
        "exit_code": process["exit_code"],
        "output_path": str(output_path),
        "pass": passed,
        "stderr_length": len(process["stderr"]),
        "stdout_length": len(process["stdout"]),
    }
    if "error" in process:
        result["error"] = process["error"]
    _write_json(evidence_dir / "controller-retrieval-result.json", result)
    return result


def _parse_job_id(stdout: bytes) -> str | None:
    text = stdout.decode("utf-8", errors="strict").strip()
    candidate = text.split(";", 1)[0]
    return candidate if re.fullmatch(r"[0-9]+", candidate) else None


def submit_with_controller_attestation(
    source_script: Path,
    *,
    evidence_dir: Path,
    sbatch: Path = Path("/slurm/bin/sbatch"),
    scontrol: Path = Path("/slurm/bin/scontrol"),
    scancel: Path = Path("/slurm/bin/scancel"),
    begin: str = "now+2minutes",
) -> dict[str, object]:
    """Submit once, retrieve the controller copy, and cancel on attestation failure."""
    source_script = Path(source_script).resolve(strict=True)
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    source_digest = sha256_file(source_script)
    (evidence_dir / "source-script-digest.raw").write_bytes(
        source_digest.encode("ascii")
    )
    (evidence_dir / "source-script-path.txt").write_text(
        f"{source_script}\n", encoding="utf-8", newline="\n"
    )
    submission_executables = {
        "sbatch": Path(sbatch),
        "scancel": Path(scancel),
        "scontrol": Path(scontrol),
    }
    executable_rows = [
        {
            "executable": name,
            "path": str(path),
            "present": path.is_file() and os.access(path, os.X_OK),
        }
        for name, path in sorted(submission_executables.items())
    ]
    executable_audit = {
        "executables": executable_rows,
        "pass": all(row["present"] for row in executable_rows),
        "schema": "controller-attestation-executable-audit-v1",
    }
    _write_json(evidence_dir / "submission-executable-audit.json", executable_audit)
    if not executable_audit["pass"]:
        result = {
            "attestation": None,
            "cancelled": False,
            "error": "mandatory Slurm submission executable is unavailable",
            "job_id": None,
            "label": ATTESTATION_FAILURE,
            "pass": False,
            "schema": "slurm-controller-attested-submission-v1",
            "source_digest": source_digest,
            "submission_once": False,
        }
        _write_json(evidence_dir / "attested-submission-result.json", result)
        return result
    submit = _run_process(
        (
            str(sbatch),
            "--parsable",
            "--export=NONE",
            f"--begin={begin}",
            str(source_script),
        )
    )
    _preserve_process(evidence_dir / "submission", submit)
    job_id = _parse_job_id(submit["stdout"]) if submit["exit_code"] == 0 else None
    result: dict[str, Any] = {
        "attestation": None,
        "cancelled": False,
        "job_id": job_id,
        "label": ATTESTATION_FAILURE,
        "pass": False,
        "schema": "slurm-controller-attested-submission-v1",
        "source_digest": source_digest,
        "submission_exit_code": submit["exit_code"],
        "submission_once": True,
    }
    if job_id is None:
        result["error"] = "sbatch did not return a valid numeric job ID"
        _write_json(evidence_dir / "attested-submission-result.json", result)
        return result

    try:
        controller_path = evidence_dir / "controller-batch-script.sbatch"
        retrieval = retrieve_controller_batch_script(
            job_id,
            controller_path,
            evidence_dir=evidence_dir,
            scontrol=scontrol,
        )
        result["controller_retrieval"] = retrieval
        if retrieval["pass"]:
            attestation = attest_batch_script_files(
                source_script, controller_path, evidence_dir=evidence_dir
            )
        else:
            attestation = {
                "label": ATTESTATION_FAILURE,
                "pass": False,
                "reason": "controller script retrieval failed",
            }
        result["attestation"] = attestation
        result["pass"] = bool(attestation["pass"])
        result["label"] = ATTESTATION_PASS if result["pass"] else ATTESTATION_FAILURE
    except Exception as error:  # cancellation below still protects the submitted job
        result["error"] = f"{type(error).__name__}: {error}"

    if not result["pass"]:
        cancel = _run_process((str(scancel), job_id))
        _preserve_process(evidence_dir / "cancellation", cancel)
        result["cancel_exit_code"] = cancel["exit_code"]
        result["cancelled"] = cancel["exit_code"] == 0
    _write_json(evidence_dir / "attested-submission-result.json", result)
    return result


def observe_running_script(raw_path: str, record: Path) -> dict[str, object]:
    """Best-effort observation of a compute-side script; never a runtime gate."""
    path = Path(raw_path)
    result: dict[str, object] = {
        "blocking": False,
        "exists": path.exists(),
        "hash_exit_status": 1,
        "inspection_available": False,
        "raw_path": raw_path,
        "readable": path.is_file() and os.access(path, os.R_OK),
        "schema": "running-batch-script-observation-v1",
    }
    try:
        result["resolved_path"] = str(path.resolve(strict=True))
        result["sha256"] = sha256_file(path)
        result["hash_exit_status"] = 0
        result["inspection_available"] = True
    except (OSError, FileDigestError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    _write_json(Path(record), result)
    return result


def classify_job_25371_attestation(
    *, fixture: dict[str, object], script: str
) -> dict[str, object]:
    """Classify the preserved 25371 evidence without inventing missing operands."""
    hashes = {
        fixture.get("source_sha256"),
        fixture.get("submitted_sha256"),
        fixture.get("controller_sha256"),
    }
    copies_match = len(hashes) == 1 and None not in hashes
    operands_preserved = bool(
        fixture.get("compute_expected_digest_preserved")
        and fixture.get("compute_actual_digest_preserved")
    )
    old_self_gate = (
        "SUBMITTED_SCRIPT_SHA256" in script
        and "actual_script_sha256" in script
        and "sha256sum" in script
    )
    return {
        "copies_match": copies_match,
        "exact_comparison_cause_confirmed": False,
        "in_job_operands_preserved": operands_preserved,
        "label": CAUSE_UNCONFIRMED,
        "old_self_hash_gate_present": old_self_gate,
        "root_cause_category": "BATCH_SCRIPT_ATTESTATION_IMPLEMENTATION_FAILURE",
        "script_mutation": False,
    }
