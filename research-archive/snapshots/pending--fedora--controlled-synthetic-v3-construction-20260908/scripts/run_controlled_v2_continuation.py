#!/usr/bin/env python3
"""Append-only continuation harness for unaccepted controlled-v2 families."""

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

from scripts.controlled_v2_catalog import FAMILIES, FAMILY_BY_ID  # noqa: E402
import scripts.freeze_controlled_v2_continuation as freeze  # noqa: E402
import scripts.run_controlled_v2_constructors as base  # noqa: E402


COHORT_ROOT = Path("synthetic_triplets/controlled_v2")
CONTINUATION_ROOT = Path("synthetic_triplets/controlled_v2_continuation")
RAW_ROOT = COHORT_ROOT / "acquisitions/raw"
PLAN_PATH = CONTINUATION_ROOT / "continuation_plan.json"
PROMPT_PATH = CONTINUATION_ROOT / "continuation_prompt.md"
RELEASE_PATH = CONTINUATION_ROOT / "continuation_release.json"
RELEASE_TAG = "controlled-synthetic-v2-continuation-v1"
FIRST_CONTINUATION_ATTEMPT = 4
LAST_CONTINUATION_ATTEMPT = 8


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def verify_plan() -> dict[str, Any]:
    plan = read_json(REPO_ROOT / PLAN_PATH)
    expected_order = [item.family_id for item in FAMILIES]
    if plan.get("status") != "PROSPECTIVELY_DEFINED_BEFORE_CONTINUATION_RUNS":
        raise ValueError("continuation plan is not prospectively frozen")
    if plan.get("family_order") != expected_order or plan.get("family_count") != 20:
        raise ValueError("continuation family order changed")
    policy = plan.get("attempt_policy", {})
    expected = {
        "first_continuation_attempt": FIRST_CONTINUATION_ATTEMPT,
        "last_continuation_attempt": LAST_CONTINUATION_ATTEMPT,
        "maximum_additional_attempts_per_unaccepted_family": 5,
        "independent_fresh_session_per_attempt": True,
        "feedback_from_prior_attempts": False,
        "preserve_every_attempt": True,
        "accept_first_complete_accept": True,
        "run_later_attempts_after_acceptance": False,
        "manual_patch_repair": False,
        "validator_changes": False,
        "family_input_changes": False,
        "continue_to_later_families_after_exhausted_family": True,
    }
    if policy != expected:
        raise ValueError("continuation attempt policy changed")
    eligibility = plan.get("eligibility", {})
    if not eligibility.get("accepted_families_are_never_rerun"):
        raise ValueError("continuation must never rerun accepted families")
    return plan


def verify_release(*, require_tag: bool = True) -> dict[str, Any]:
    release = freeze.verify_release()
    if release.get("continuation_attempt_range") != [4, 8]:
        raise ValueError("continuation release attempt range changed")
    if release.get("accepted_families_are_skipped") is not True:
        raise ValueError("continuation release does not skip accepted families")
    base_release = base.verify_release(require_tag=False)
    if release.get("base_filter_inventory_sha256") != base_release.get("inventory_sha256"):
        raise ValueError("continuation is not bound to the frozen base filter")
    if require_tag:
        head = base.capture(["git", "rev-parse", "HEAD"])
        tag = base.capture(["git", "rev-list", "-n", "1", RELEASE_TAG])
        if head["returncode"] or tag["returncode"]:
            raise ValueError("continuation release tag is missing")
        if head["stdout"].strip() != tag["stdout"].strip():
            raise ValueError("continuation runs require HEAD at the continuation release tag")
    return release


def attempt_name(number: int) -> str:
    if not 1 <= number <= LAST_CONTINUATION_ATTEMPT:
        raise ValueError(f"attempt number must be between 1 and {LAST_CONTINUATION_ATTEMPT}")
    return f"attempt-{number:03d}"


def attempt_root(family_id: str, number: int) -> Path:
    return REPO_ROOT / RAW_ROOT / family_id / attempt_name(number)


def construction_nonce(release: dict[str, Any], family_id: str, number: int) -> str:
    material = ":".join(
        (
            release["base_filter_inventory_sha256"],
            release["inventory_sha256"],
            family_id,
            attempt_name(number),
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def render_prompt(release: dict[str, Any], family_id: str, number: int) -> bytes:
    if not FIRST_CONTINUATION_ATTEMPT <= number <= LAST_CONTINUATION_ATTEMPT:
        raise ValueError("render_prompt is only for continuation attempts")
    template = (REPO_ROOT / PROMPT_PATH).read_text(encoding="utf-8").rstrip()
    binding = {
        "schema_version": "controlled-synthetic-v2-continuation-binding/1",
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
        + "\n\n## Frozen continuation binding\n\n```json\n"
        + json.dumps(binding, indent=2, sort_keys=True)
        + "\n```\n"
    ).encode()


def workspace_agent_text() -> str:
    return """# Isolated controlled-v2 continuation workspace

This workspace contains one frozen family and no prior attempt artifacts or
decisions. Follow the rendered prompt. Read only `inputs/` and
`tools/check_public.py`; write candidate output only under `candidate/`, with
optional temporary work under `.scratch/`. Do not inspect parent directories,
Git metadata, other families, prior attempts, sealed tests, reference
implementations, or acquisition decisions. Do not use network access. Run
`python3 tools/check_public.py`; the external harness alone decides admission.
"""


def materialize_attempt(
    family_id: str,
    number: int,
    release: dict[str, Any],
) -> dict[str, Any]:
    root = attempt_root(family_id, number)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {root}")
    workspace = root / "workspace"
    record = root / "record"
    workspace.mkdir(parents=True)
    record.mkdir()
    base.write_new(workspace / "AGENTS.md", workspace_agent_text().encode())
    hashes = {"AGENTS.md": base.sha256_file(workspace / "AGENTS.md")}
    for source, destination in base.constructor_input_files(family_id).items():
        base.copy_new(source, workspace / destination)
        hashes[destination.as_posix()] = base.sha256_file(workspace / destination)
    (workspace / "candidate").mkdir()
    prompt = render_prompt(release, family_id, number)
    base.write_new(record / "prompt.txt", prompt)
    manifest = {
        "schema_version": "controlled-synthetic-v2-continuation-render-record/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "rendered_at_utc": base.utc_now(),
        "construction_nonce": construction_nonce(release, family_id, number),
        "base_filter_inventory_sha256": release["base_filter_inventory_sha256"],
        "continuation_inventory_sha256": release["inventory_sha256"],
        "continuation_release_tag": RELEASE_TAG,
        "prompt_sha256": base.sha256_bytes(prompt),
        "allowed_input_sha256": dict(sorted(hashes.items())),
        "sealed_tests_present": False,
        "reference_states_present": False,
        "other_family_inputs_present": False,
        "prior_attempt_artifacts_present": False,
        "prior_attempt_feedback_present": False,
        "initial_workspace": base.tree_snapshot(workspace),
    }
    base.write_new_json(record / "render_manifest.json", manifest)
    return manifest


def existing_outcomes(family_id: str) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    missing_seen = False
    for number in range(1, LAST_CONTINUATION_ATTEMPT + 1):
        root = attempt_root(family_id, number)
        path = root / "record/outcome.json"
        if path.is_file():
            if missing_seen:
                raise RuntimeError(f"non-contiguous append-only attempt sequence for {family_id}")
            outcomes.append(read_json(path))
        elif root.exists():
            raise RuntimeError(f"incomplete append-only attempt requires audit: {root}")
        else:
            missing_seen = True
    return outcomes


def accepted_outcome(family_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in existing_outcomes(family_id) if item.get("machine_accepted") is True),
        None,
    )


def next_attempt_number(family_id: str) -> int | None:
    outcomes = existing_outcomes(family_id)
    if any(item.get("machine_accepted") is True for item in outcomes):
        return None
    if len(outcomes) < 3:
        raise RuntimeError(f"original three-attempt pass is incomplete for {family_id}")
    if len(outcomes) >= LAST_CONTINUATION_ATTEMPT:
        return None
    return len(outcomes) + 1


def run_attempt(family_id: str, number: int) -> dict[str, Any]:
    if not FIRST_CONTINUATION_ATTEMPT <= number <= LAST_CONTINUATION_ATTEMPT:
        raise ValueError("continuation runner may create only attempts 4 through 8")
    plan = verify_plan()
    release = verify_release(require_tag=True)
    manifest = materialize_attempt(family_id, number, release)
    root = attempt_root(family_id, number)
    workspace = root / "workspace"
    record = root / "record"
    prompt = (record / "prompt.txt").read_bytes()
    if base.sha256_bytes(prompt) != manifest["prompt_sha256"]:
        raise ValueError("rendered continuation prompt hash mismatch")
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
            "continuation_release_tag": RELEASE_TAG,
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
    validation = base.validate_attempt(family_id, workspace / "candidate")
    base.write_new_json(record / "validation.json", validation)
    base.write_new_json(record / "workspace_final_snapshot.json", base.tree_snapshot(workspace))
    outcome = {
        "schema_version": "controlled-synthetic-v2-continuation-attempt-outcome/1",
        "family_id": family_id,
        "attempt": attempt_name(number),
        "completed_at_utc": base.utc_now(),
        "execution": execution,
        "candidate_snapshot": base.tree_snapshot(workspace / "candidate"),
        "validation_sha256": base.sha256_file(record / "validation.json"),
        "terminal_reason": validation.get("terminal_reason", "REJECT"),
        "machine_accepted": validation.get("machine_accepted") is True,
        "accepted_families_skipped": True,
        "prior_attempt_feedback_exposed": False,
        "first_pass_policy": "accept immediately if COMPLETE_ACCEPT; never compare candidates",
    }
    base.write_new_json(record / "outcome.json", outcome)
    return outcome


def run_family(family_id: str) -> dict[str, Any]:
    if family_id not in FAMILY_BY_ID:
        raise ValueError(f"unknown family: {family_id}")
    before = existing_outcomes(family_id)
    accepted_before = next((item for item in before if item.get("machine_accepted") is True), None)
    while not accepted_before:
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
        "accepted_family_was_skipped": accepted_before is not None,
        "continuation_exhausted": accepted is None and len(outcomes) == LAST_CONTINUATION_ATTEMPT,
    }


def status() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in FAMILIES:
        outcomes = existing_outcomes(item.family_id)
        accepted = next((row for row in outcomes if row.get("machine_accepted") is True), None)
        if accepted:
            state = "COMPLETE_ACCEPT"
        elif len(outcomes) == LAST_CONTINUATION_ATTEMPT:
            state = "EXHAUSTED_CONTINUATION"
        elif len(outcomes) < 3:
            state = "ORIGINAL_PASS_INCOMPLETE"
        else:
            state = "ELIGIBLE"
        rows.append(
            {
                "family_id": item.family_id,
                "attempts_total": len(outcomes),
                "accepted_attempt": accepted.get("attempt") if accepted else None,
                "state": state,
            }
        )
    return {
        "schema_version": "controlled-synthetic-v2-continuation-status/1",
        "families": rows,
        "accepted_count": sum(row["state"] == "COMPLETE_ACCEPT" for row in rows),
        "exhausted_count": sum(row["state"] == "EXHAUSTED_CONTINUATION" for row in rows),
        "eligible_count": sum(row["state"] == "ELIGIBLE" for row in rows),
        "original_incomplete_count": sum(
            row["state"] == "ORIGINAL_PASS_INCOMPLETE" for row in rows
        ),
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
