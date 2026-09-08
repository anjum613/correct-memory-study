#!/usr/bin/env python3
"""Append-only, first-pass Codex acquisition harness for controlled synthetic v2."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILIES, FAMILY_BY_ID  # noqa: E402
from scripts.validate_controlled_triplet_v2 import (  # noqa: E402
    AdmissionError,
    validate_candidate,
)


COHORT_ROOT = Path("synthetic_triplets/controlled_v2")
RAW_ROOT = COHORT_ROOT / "acquisitions/raw"
PLAN_PATH = COHORT_ROOT / "cohort_plan.json"
PROMPT_PATH = COHORT_ROOT / "generator_prompt.md"
RELEASE_PATH = COHORT_ROOT / "filter_release.json"
PUBLIC_CHECKER_PATH = Path("scripts/check_controlled_v2_public.py")
RELEASE_TAG = "controlled-synthetic-v2-filter-v1"
DEFAULT_CODEX = "/home/s224049759/.local/bin/codex"
DEFAULT_TIMEOUT = 1800
POST_TERMINAL_GRACE_SECONDS = 15.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def write_new_json(path: Path, value: object) -> None:
    write_new(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def copy_new(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"input is missing or not regular: {source}")
    write_new(destination, source.read_bytes())


def capture(command: list[str], *, cwd: Path = REPO_ROOT) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def verify_plan() -> dict[str, Any]:
    plan = read_json(REPO_ROOT / PLAN_PATH)
    expected_order = [item.family_id for item in FAMILIES]
    if plan.get("status") != "PROSPECTIVELY_DEFINED_BEFORE_CONSTRUCTOR_RUNS":
        raise ValueError("construction plan is not prospectively frozen")
    if plan.get("family_order") != expected_order or plan.get("family_count") != 20:
        raise ValueError("construction plan family order changed")
    policy = plan.get("attempt_policy")
    expected_policy = {
        "maximum_attempts_per_family": 3,
        "independent_fresh_session_per_attempt": True,
        "feedback_from_prior_attempts": False,
        "preserve_every_attempt": True,
        "accept_first_complete_accept": True,
        "run_later_attempts_after_acceptance": False,
        "manual_patch_repair": False,
        "outcome_based_family_replacement": False,
        "continue_to_later_families_after_exhausted_family": True,
    }
    if policy != expected_policy:
        raise ValueError("construction attempt policy changed")
    return plan


def verify_release(*, require_tag: bool = True) -> dict[str, Any]:
    release = read_json(REPO_ROOT / RELEASE_PATH)
    if release.get("schema_version") != "controlled-synthetic-v2-filter-release/1":
        raise ValueError("unexpected filter release schema")
    if release.get("status") != "FROZEN_PRE_CONSTRUCTION":
        raise ValueError("filter release is not pre-construction")
    if release.get("family_count") != 20 or release.get("release_tag") != RELEASE_TAG:
        raise ValueError("filter release cohort identity changed")
    files = release.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("filter release has no file inventory")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, dict):
            raise ValueError("malformed filter release inventory")
        path = REPO_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"released input missing: {relative}")
        observed = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        if observed != expected:
            raise ValueError(f"released input changed: {relative}")
    if require_tag:
        head = capture(["git", "rev-parse", "HEAD"])
        tag = capture(["git", "rev-list", "-n", "1", RELEASE_TAG])
        if head["returncode"] or tag["returncode"]:
            raise ValueError("filter release tag is missing")
        if head["stdout"].strip() != tag["stdout"].strip():
            raise ValueError("constructor runs require HEAD at the filter release tag")
    return release


def attempt_name(number: int) -> str:
    if number not in (1, 2, 3):
        raise ValueError("attempt number must be 1, 2, or 3")
    return f"attempt-{number:03d}"


def attempt_root(family_id: str, number: int) -> Path:
    return REPO_ROOT / RAW_ROOT / family_id / attempt_name(number)


def family_materialized_root(family_id: str) -> Path:
    item = FAMILY_BY_ID[family_id]
    return REPO_ROOT / COHORT_ROOT / "families" / f"{family_id.lower()}-{item.slug}"


def constructor_input_files(family_id: str) -> dict[Path, Path]:
    family_root = family_materialized_root(family_id)
    mappings: dict[Path, Path] = {
        REPO_ROOT / COHORT_ROOT / "family_specs" / f"{family_id}.json": Path("inputs/spec.json"),
        REPO_ROOT / PUBLIC_CHECKER_PATH: Path("tools/check_public.py"),
    }
    for source in sorted((family_root / "source").rglob("*")):
        if source.is_file():
            mappings[source] = Path("inputs/source") / source.relative_to(family_root / "source")
    target_root = family_root / "target"
    for source in sorted(target_root.rglob("*")):
        if source.is_file():
            mappings[source] = Path("inputs/target") / source.relative_to(target_root)
    return mappings


def workspace_agent_text() -> str:
    return """# Isolated controlled-v2 constructor workspace

This workspace contains one prospectively frozen family. Follow the rendered
prompt. Read only `inputs/` and `tools/check_public.py`; write candidate output
only under `candidate/`, with optional temporary work under `.scratch/`. Do not
inspect parent directories, Git metadata, other families, prior attempts, sealed
tests, reference implementations, or acquisition decisions. Do not use network
access. The only relevant check available here is
`python tools/check_public.py`; the external harness makes admission decisions.
"""


def construction_nonce(release: dict[str, Any], family_id: str, number: int) -> str:
    material = f"{release['inventory_sha256']}:{family_id}:{attempt_name(number)}"
    return sha256_bytes(material.encode())


def render_prompt(release: dict[str, Any], family_id: str, number: int) -> bytes:
    template = (REPO_ROOT / PROMPT_PATH).read_text(encoding="utf-8").rstrip()
    binding = {
        "schema_version": "controlled-synthetic-v2-constructor-binding/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "construction_nonce": construction_nonce(release, family_id, number),
        "construction_nonce_is_not_sampling_seed": True,
        "sampling_seed": None,
        "prior_attempt_feedback": False,
        "candidate_directory": "candidate",
        "public_check_command": "python tools/check_public.py",
        "allowed_read_roots": ["inputs", "tools/check_public.py"],
        "allowed_write_roots": ["candidate", ".scratch"],
    }
    return (
        template
        + "\n\n## Frozen run binding\n\n```json\n"
        + json.dumps(binding, indent=2, sort_keys=True)
        + "\n```\n"
    ).encode()


def tree_snapshot(root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                entries.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
            elif path.is_file():
                entries.append(
                    {
                        "path": relative,
                        "type": "file",
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            elif path.is_dir():
                entries.append({"path": relative, "type": "directory"})
    return {
        "exists": root.exists(),
        "entries": entries,
        "tree_sha256": sha256_bytes(json.dumps(entries, sort_keys=True).encode()),
    }


def materialize_attempt(family_id: str, number: int, release: dict[str, Any]) -> dict[str, Any]:
    root = attempt_root(family_id, number)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {root}")
    workspace = root / "workspace"
    record = root / "record"
    workspace.mkdir(parents=True)
    record.mkdir()
    write_new(workspace / "AGENTS.md", workspace_agent_text().encode())
    hashes = {"AGENTS.md": sha256_file(workspace / "AGENTS.md")}
    for source, destination in constructor_input_files(family_id).items():
        copy_new(source, workspace / destination)
        hashes[destination.as_posix()] = sha256_file(workspace / destination)
    (workspace / "candidate").mkdir()
    prompt = render_prompt(release, family_id, number)
    write_new(record / "prompt.txt", prompt)
    manifest = {
        "schema_version": "controlled-synthetic-v2-render-record/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "rendered_at_utc": utc_now(),
        "construction_nonce": construction_nonce(release, family_id, number),
        "release_inventory_sha256": release["inventory_sha256"],
        "release_tag": RELEASE_TAG,
        "prompt_sha256": sha256_bytes(prompt),
        "allowed_input_sha256": dict(sorted(hashes.items())),
        "sealed_tests_present": False,
        "reference_states_present": False,
        "other_family_inputs_present": False,
        "prior_attempt_feedback_present": False,
        "initial_workspace": tree_snapshot(workspace),
    }
    write_new_json(record / "render_manifest.json", manifest)
    return manifest


def codex_command(workspace: Path, final_message: Path, plan: dict[str, Any]) -> list[str]:
    config = plan["constructor"]
    return [
        DEFAULT_CODEX,
        "--ask-for-approval",
        "never",
        "exec",
        "--ignore-user-config",
        "--strict-config",
        "--model",
        config["model"],
        "--config",
        f'model_reasoning_effort="{config["reasoning_effort"]}"',
        "--sandbox",
        config["sandbox"],
        "--cd",
        str(workspace),
        "--skip-git-repo-check",
        "--json",
        "--color",
        "never",
        "--output-last-message",
        str(final_message),
        "-",
    ]


def terminal_event_present(path: Path) -> bool:
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") in {"turn.completed", "turn.failed"}:
            return True
    return False


def execute_codex(
    command: list[str],
    *,
    workspace: Path,
    prompt: bytes,
    events: Path,
    stderr: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    terminal_seen_at: float | None = None
    timed_out = False
    termination_reason = "PROCESS_EXIT"
    with events.open("xb") as stdout_handle, stderr.open("xb") as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()
        while process.poll() is None:
            now = time.monotonic()
            if terminal_seen_at is None and terminal_event_present(events):
                terminal_seen_at = now
            if terminal_seen_at is not None and now - terminal_seen_at >= POST_TERMINAL_GRACE_SECONDS:
                termination_reason = "TERMINATED_AFTER_RECORDED_TERMINAL_EVENT"
                process.terminate()
                break
            if now - started >= timeout_seconds:
                timed_out = True
                termination_reason = "TIMEOUT"
                process.terminate()
                break
            time.sleep(0.25)
        try:
            returncode = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
            termination_reason += "_THEN_KILLED"
    return {
        "returncode": returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "termination_reason": termination_reason,
        "terminal_event_present": terminal_event_present(events),
    }


def validate_attempt(family_id: str, candidate: Path) -> dict[str, Any]:
    try:
        return validate_candidate(family_id, candidate)
    except (AdmissionError, FileNotFoundError, OSError, UnicodeError) as error:
        return {
            "schema_version": "controlled-synthetic-v2-admission/1",
            "family_id": family_id,
            "terminal_reason": "REJECT",
            "machine_accepted": False,
            "fatal_error": str(error),
            "checks": [],
        }


def run_attempt(family_id: str, number: int) -> dict[str, Any]:
    plan = verify_plan()
    release = verify_release(require_tag=True)
    root = attempt_root(family_id, number)
    if root.exists():
        raise FileExistsError(f"attempt already exists: {root}")
    manifest = materialize_attempt(family_id, number, release)
    workspace = root / "workspace"
    record = root / "record"
    prompt = (record / "prompt.txt").read_bytes()
    if sha256_bytes(prompt) != manifest["prompt_sha256"]:
        raise ValueError("rendered prompt hash mismatch")
    command = codex_command(workspace, record / "final_message.txt", plan)
    write_new_json(
        record / "started.json",
        {
            "family_id": family_id,
            "attempt": attempt_name(number),
            "started_at_utc": utc_now(),
            "command": command,
            "codex_version": capture([DEFAULT_CODEX, "--version"]),
            "python": sys.version,
            "platform": platform.platform(),
        },
    )
    execution = execute_codex(
        command,
        workspace=workspace,
        prompt=prompt,
        events=record / "events.jsonl",
        stderr=record / "stderr.log",
        timeout_seconds=int(plan["constructor"]["timeout_seconds"]),
    )
    validation = validate_attempt(family_id, workspace / "candidate")
    write_new_json(record / "validation.json", validation)
    write_new_json(record / "workspace_final_snapshot.json", tree_snapshot(workspace))
    outcome = {
        "schema_version": "controlled-synthetic-v2-attempt-outcome/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "completed_at_utc": utc_now(),
        "execution": execution,
        "candidate_snapshot": tree_snapshot(workspace / "candidate"),
        "validation_sha256": sha256_file(record / "validation.json"),
        "terminal_reason": validation.get("terminal_reason", "REJECT"),
        "machine_accepted": validation.get("machine_accepted") is True,
        "first_pass_policy": "accept immediately if COMPLETE_ACCEPT; never compare candidates",
    }
    write_new_json(record / "outcome.json", outcome)
    return outcome


def existing_outcomes(family_id: str) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for number in (1, 2, 3):
        path = attempt_root(family_id, number) / "record/outcome.json"
        if path.is_file():
            outcomes.append(read_json(path))
        elif attempt_root(family_id, number).exists():
            raise RuntimeError(f"incomplete append-only attempt requires audit: {attempt_root(family_id, number)}")
        else:
            break
    return outcomes


def next_attempt_number(family_id: str) -> int | None:
    outcomes = existing_outcomes(family_id)
    if any(item.get("machine_accepted") is True for item in outcomes):
        return None
    if len(outcomes) >= 3:
        return None
    return len(outcomes) + 1


def run_family(family_id: str) -> dict[str, Any]:
    if family_id not in FAMILY_BY_ID:
        raise ValueError(f"unknown family: {family_id}")
    while True:
        number = next_attempt_number(family_id)
        if number is None:
            break
        outcome = run_attempt(family_id, number)
        if outcome["machine_accepted"]:
            break
    outcomes = existing_outcomes(family_id)
    accepted = next((item for item in outcomes if item.get("machine_accepted") is True), None)
    return {
        "family_id": family_id,
        "attempts_run": len(outcomes),
        "machine_accepted": accepted is not None,
        "accepted_attempt": accepted["attempt"] if accepted else None,
        "exhausted": accepted is None and len(outcomes) == 3,
    }


def status() -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    for item in FAMILIES:
        outcomes = existing_outcomes(item.family_id)
        accepted = next((row for row in outcomes if row.get("machine_accepted") is True), None)
        families.append(
            {
                "family_id": item.family_id,
                "attempts_run": len(outcomes),
                "accepted_attempt": accepted.get("attempt") if accepted else None,
                "state": (
                    "COMPLETE_ACCEPT"
                    if accepted
                    else "EXHAUSTED"
                    if len(outcomes) == 3
                    else "PENDING"
                ),
            }
        )
    return {
        "schema_version": "controlled-synthetic-v2-construction-status/1",
        "families": families,
        "accepted_count": sum(row["state"] == "COMPLETE_ACCEPT" for row in families),
        "exhausted_count": sum(row["state"] == "EXHAUSTED" for row in families),
        "pending_count": sum(row["state"] == "PENDING" for row in families),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=sorted(FAMILY_BY_ID))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify-release", action="store_true")
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.family, args.all, args.status, args.verify_release))
    if selected != 1:
        parser.error("choose exactly one of --family, --all, --status, or --verify-release")
    if args.verify_release:
        result: object = verify_release(require_tag=True)
    elif args.status:
        result = status()
    elif args.family:
        result = run_family(args.family)
    else:
        results = [run_family(item.family_id) for item in FAMILIES]
        result = {"families": results, "status": status()}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
