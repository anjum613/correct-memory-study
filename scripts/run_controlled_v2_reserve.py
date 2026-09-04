#!/usr/bin/env python3
"""Append-only constructor harness for the frozen controlled-v2 reserve queue."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reserve_catalog_v2 import FAMILIES, FAMILY_BY_ID  # noqa: E402
import scripts.freeze_controlled_v2_reserve as freeze  # noqa: E402
import scripts.run_controlled_v2_constructors as base  # noqa: E402
from scripts.validate_controlled_triplet_v2_reserve import (  # noqa: E402
    validate_candidate,
)


RESERVE_ROOT = Path("synthetic_triplets/controlled_v2_reserve")
RAW_ROOT = RESERVE_ROOT / "acquisitions/raw"
PLAN_PATH = RESERVE_ROOT / "reserve_plan.json"
PROMPT_PATH = RESERVE_ROOT / "generator_prompt.md"
RELEASE_TAG = "controlled-synthetic-v2-reserve-v2"
MAX_ATTEMPTS = 5


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def verify_plan() -> dict[str, Any]:
    plan = read_json(REPO_ROOT / PLAN_PATH)
    if plan.get("status") != "FROZEN_BEFORE_ANY_RESERVE_CONSTRUCTOR_RUN":
        raise ValueError("reserve plan is not frozen")
    if plan.get("reserve_order") != [item.family_id for item in FAMILIES]:
        raise ValueError("reserve order changed")
    if plan.get("reserve_family_count") != len(FAMILIES):
        raise ValueError("reserve family count changed")
    expected_policy = {
        "maximum_attempts_per_reserve_family": MAX_ATTEMPTS,
        "independent_fresh_session_per_attempt": True,
        "feedback_from_prior_attempts": False,
        "preserve_every_attempt": True,
        "accept_first_complete_accept": True,
        "run_later_attempts_after_acceptance": False,
        "manual_patch_repair": False,
        "continue_to_next_reserve_after_exhaustion": True,
    }
    if plan.get("attempt_policy") != expected_policy:
        raise ValueError("reserve attempt policy changed")
    if plan.get("selection_policy", {}).get("rerun_previously_accepted_families") is not False:
        raise ValueError("reserve plan could rerun accepted originals")
    return plan


def verify_release(*, require_tag: bool = True) -> dict[str, Any]:
    release = freeze.verify_release()
    if release.get("reserve_order") != [item.family_id for item in FAMILIES]:
        raise ValueError("reserve release order changed")
    if require_tag:
        head = base.capture(["git", "rev-parse", "HEAD"])
        tag = base.capture(["git", "rev-list", "-n", "1", RELEASE_TAG])
        if head["returncode"] or tag["returncode"]:
            raise ValueError("reserve release tag is missing")
        if head["stdout"].strip() != tag["stdout"].strip():
            raise ValueError("reserve runs require HEAD at the reserve release tag")
    return release


def attempt_name(number: int) -> str:
    if not 1 <= number <= MAX_ATTEMPTS:
        raise ValueError(f"attempt number must be between 1 and {MAX_ATTEMPTS}")
    return f"attempt-{number:03d}"


def attempt_root(family_id: str, number: int) -> Path:
    return REPO_ROOT / RAW_ROOT / family_id / attempt_name(number)


def materialized_root(family_id: str) -> Path:
    item = FAMILY_BY_ID[family_id]
    return REPO_ROOT / RESERVE_ROOT / "families" / f"{family_id.lower()}-{item.slug}"


def constructor_input_files(family_id: str) -> dict[Path, Path]:
    root = materialized_root(family_id)
    mappings: dict[Path, Path] = {
        REPO_ROOT / RESERVE_ROOT / "family_specs" / f"{family_id}.json": Path("inputs/spec.json"),
        REPO_ROOT / "scripts/check_controlled_v2_public.py": Path("tools/check_public.py"),
    }
    for source in sorted((root / "source").rglob("*")):
        if source.is_file():
            mappings[source] = Path("inputs/source") / source.relative_to(root / "source")
    for source in sorted((root / "target").rglob("*")):
        if source.is_file():
            mappings[source] = Path("inputs/target") / source.relative_to(root / "target")
    return mappings


def construction_nonce(release: dict[str, Any], family_id: str, number: int) -> str:
    material = f"{release['inventory_sha256']}:{family_id}:{attempt_name(number)}"
    return hashlib.sha256(material.encode()).hexdigest()


def render_prompt(release: dict[str, Any], family_id: str, number: int) -> bytes:
    template = (REPO_ROOT / PROMPT_PATH).read_text(encoding="utf-8").rstrip()
    binding = {
        "schema_version": "controlled-synthetic-v2-reserve-binding/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "construction_nonce": construction_nonce(release, family_id, number),
        "construction_nonce_is_not_sampling_seed": True,
        "sampling_seed": None,
        "prior_attempt_feedback": False,
        "prior_attempt_artifacts_present": False,
        "candidate_directory": "candidate",
        "public_check_command": "python3 tools/check_public.py",
        "allowed_read_roots": ["inputs", "tools/check_public.py"],
        "allowed_write_roots": ["candidate", ".scratch"],
    }
    return (
        template
        + "\n\n## Frozen reserve binding\n\n```json\n"
        + json.dumps(binding, indent=2, sort_keys=True)
        + "\n```\n"
    ).encode()


def workspace_agent_text() -> str:
    return """# Isolated controlled-v2 reserve workspace

This workspace contains one frozen reserve family. Follow the rendered prompt.
Read only `inputs/` and `tools/check_public.py`; write candidate output only under
`candidate/`, with optional temporary work under `.scratch/`. Do not inspect
parent directories, Git metadata, other families, earlier attempts, sealed tests,
reference implementations, or acquisition decisions. Do not use network access.
Run `python3 tools/check_public.py`; the external harness decides admission.
"""


def materialize_attempt(
    family_id: str,
    number: int,
    release: dict[str, Any],
) -> dict[str, Any]:
    root = attempt_root(family_id, number)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite reserve attempt: {root}")
    workspace = root / "workspace"
    record = root / "record"
    workspace.mkdir(parents=True)
    record.mkdir()
    base.write_new(workspace / "AGENTS.md", workspace_agent_text().encode())
    hashes = {"AGENTS.md": base.sha256_file(workspace / "AGENTS.md")}
    for source, destination in constructor_input_files(family_id).items():
        base.copy_new(source, workspace / destination)
        hashes[destination.as_posix()] = base.sha256_file(workspace / destination)
    (workspace / "candidate").mkdir()
    prompt = render_prompt(release, family_id, number)
    base.write_new(record / "prompt.txt", prompt)
    manifest = {
        "schema_version": "controlled-synthetic-v2-reserve-render-record/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "rendered_at_utc": base.utc_now(),
        "construction_nonce": construction_nonce(release, family_id, number),
        "reserve_inventory_sha256": release["inventory_sha256"],
        "reserve_release_tag": RELEASE_TAG,
        "prompt_sha256": base.sha256_bytes(prompt),
        "allowed_input_sha256": dict(sorted(hashes.items())),
        "sealed_tests_present": False,
        "reference_states_present": False,
        "other_family_inputs_present": False,
        "prior_attempt_feedback_present": False,
        "initial_workspace": base.tree_snapshot(workspace),
    }
    base.write_new_json(record / "render_manifest.json", manifest)
    return manifest


def existing_outcomes(family_id: str) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for number in range(1, MAX_ATTEMPTS + 1):
        root = attempt_root(family_id, number)
        path = root / "record/outcome.json"
        if path.is_file():
            outcomes.append(read_json(path))
        elif root.exists():
            raise RuntimeError(f"incomplete append-only reserve attempt requires audit: {root}")
        else:
            break
    return outcomes


def next_attempt_number(family_id: str) -> int | None:
    outcomes = existing_outcomes(family_id)
    if any(item.get("machine_accepted") is True for item in outcomes):
        return None
    if len(outcomes) >= MAX_ATTEMPTS:
        return None
    return len(outcomes) + 1


def validate_attempt(family_id: str, candidate: Path) -> dict[str, Any]:
    try:
        return validate_candidate(family_id, candidate)
    except (base.AdmissionError, FileNotFoundError, OSError, UnicodeError) as error:
        return {
            "schema_version": "controlled-synthetic-v2-admission/1",
            "family_id": family_id,
            "terminal_reason": "REJECT",
            "machine_accepted": False,
            "fatal_error": str(error),
            "checks": [],
            "validator_implementation": "scripts/validate_controlled_triplet_v2.py",
            "reserve_catalog_adapter_only": True,
        }


def run_attempt(family_id: str, number: int) -> dict[str, Any]:
    plan = verify_plan()
    release = verify_release(require_tag=True)
    manifest = materialize_attempt(family_id, number, release)
    root = attempt_root(family_id, number)
    workspace = root / "workspace"
    record = root / "record"
    prompt = (record / "prompt.txt").read_bytes()
    if base.sha256_bytes(prompt) != manifest["prompt_sha256"]:
        raise ValueError("rendered reserve prompt hash mismatch")
    command = base.codex_command(workspace, record / "final_message.txt", plan)
    base.write_new_json(
        record / "started.json",
        {
            "family_id": family_id,
            "attempt": attempt_name(number),
            "started_at_utc": base.utc_now(),
            "command": command,
            "codex_version": base.capture([base.DEFAULT_CODEX, "--version"]),
            "python": sys.version,
            "platform": platform.platform(),
            "reserve_release_tag": RELEASE_TAG,
        },
    )
    execution = base.execute_codex(
        command,
        workspace=workspace,
        prompt=prompt,
        events=record / "events.jsonl",
        stderr=record / "stderr.log",
        timeout_seconds=int(plan["constructor"]["timeout_seconds"]),
    )
    validation = validate_attempt(family_id, workspace / "candidate")
    base.write_new_json(record / "validation.json", validation)
    base.write_new_json(record / "workspace_final_snapshot.json", base.tree_snapshot(workspace))
    outcome = {
        "schema_version": "controlled-synthetic-v2-reserve-attempt-outcome/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "completed_at_utc": base.utc_now(),
        "execution": execution,
        "candidate_snapshot": base.tree_snapshot(workspace / "candidate"),
        "validation_sha256": base.sha256_file(record / "validation.json"),
        "terminal_reason": validation.get("terminal_reason", "REJECT"),
        "machine_accepted": validation.get("machine_accepted") is True,
        "prior_attempt_feedback_exposed": False,
        "first_pass_policy": "accept immediately if COMPLETE_ACCEPT; never compare candidates",
    }
    base.write_new_json(record / "outcome.json", outcome)
    return outcome


def run_family(family_id: str) -> dict[str, Any]:
    if family_id not in FAMILY_BY_ID:
        raise ValueError(f"unknown reserve family: {family_id}")
    before = existing_outcomes(family_id)
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
        "attempts_total": len(outcomes),
        "attempts_added": len(outcomes) - len(before),
        "machine_accepted": accepted is not None,
        "accepted_attempt": accepted["attempt"] if accepted else None,
        "exhausted": accepted is None and len(outcomes) == MAX_ATTEMPTS,
    }


def status() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in FAMILIES:
        outcomes = existing_outcomes(item.family_id)
        accepted = next((row for row in outcomes if row.get("machine_accepted") is True), None)
        rows.append(
            {
                "family_id": item.family_id,
                "attempts_total": len(outcomes),
                "accepted_attempt": accepted.get("attempt") if accepted else None,
                "state": (
                    "COMPLETE_ACCEPT"
                    if accepted
                    else "EXHAUSTED"
                    if len(outcomes) == MAX_ATTEMPTS
                    else "AVAILABLE"
                ),
            }
        )
    return {
        "schema_version": "controlled-synthetic-v2-reserve-status/1",
        "families": rows,
        "accepted_count": sum(row["state"] == "COMPLETE_ACCEPT" for row in rows),
        "exhausted_count": sum(row["state"] == "EXHAUSTED" for row in rows),
        "available_count": sum(row["state"] == "AVAILABLE" for row in rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=sorted(FAMILY_BY_ID))
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify-release", action="store_true")
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.family, args.status, args.verify_release))
    if selected != 1:
        parser.error("choose exactly one of --family, --status, or --verify-release")
    if args.verify_release:
        result: object = verify_release(require_tag=True)
    elif args.status:
        result = status()
    else:
        result = run_family(args.family)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
