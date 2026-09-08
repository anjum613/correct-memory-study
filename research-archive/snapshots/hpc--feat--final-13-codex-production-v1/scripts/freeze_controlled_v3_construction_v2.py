#!/usr/bin/env python3
"""Create the pre-construction runtime amendment for controlled V3 construction V2.

This script performs exactly one non-benchmark Codex accessibility invocation.
It never materializes an X-family input and cannot start a constructor attempt.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_controlled_v3_pool as v1_launcher  # noqa: E402
from scripts import v3_difficulty_envelope as difficulty_envelope  # noqa: E402


BASE_FREEZE_COMMIT = "d2799394625e7ada8256daa4a1005e4c88b1e21a"
DIFFICULTY_RELEASE_ID = "controlled-synthetic-v3-difficulty-amendment-v1"
DIFFICULTY_MANIFEST_SHA256 = "e9076e48aa465c9a921da98fcd0accaefc957a84116ac4b0d6bbdc1c9e0e4403"
V1_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v1"
V1_TREE_SHA256 = "899f47535854e79060ec6a70ae12ca61f31b67d294e2f596de19034adacc2afb"
V1_FILE_COUNT = 27
V2_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v2"
V2_RELEASE_ID = "controlled-v3-construction-v2-runtime-amendment-v1"
CODEX = Path("/home/s224049759/.local/bin/codex")
USER_CONFIG = Path("/home/s224049759/.codex/config.toml")

MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "max"
FAST_MODE_ENABLED = False
SERVICE_TIER = "default"
TIMEOUT_SECONDS = 600
TOOL_CALL_LIMIT = 60
MAXIMUM_OUTPUT_TOKENS = 16_384

IN_SCOPE = (
    "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08", "X09",
    "X10", "X11", "X12", "X13", "X14", "X15", "X16", "X17", "X18",
    "X20", "X21", "X22", "X23", "X24", "X26", "X27", "X28",
)
EXCLUDED = ("X19", "X25")

DUMMY_ACK = "CONTROLLED_V3_CONSTRUCTION_V2_RUNTIME_ACCESS_OK"
DUMMY_PROMPT = (
    "This is a non-benchmark constructor-runtime accessibility check. "
    "No benchmark task, family specification, candidate, test, validator, prior output, "
    "or human judgment is present. Do not inspect files and do not call tools. "
    f"Reply with exactly {DUMMY_ACK} and nothing else.\n"
)
DUMMY_AGENTS = """# Non-benchmark runtime accessibility workspace

This empty workspace is solely for one constructor-runtime accessibility check.
No benchmark input is present. Do not inspect files, call tools, or make changes.
Return only the exact acknowledgment requested by the prompt.
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def write_new_json(path: Path, value: object) -> None:
    write_new(path, json.dumps(value, indent=2, sort_keys=True, default=repr).encode("utf-8") + b"\n")


def capture(command: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def inventory_tree(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            rows.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        elif stat.S_ISREG(metadata.st_mode):
            rows.append({
                "path": relative,
                "type": "file",
                "bytes": metadata.st_size,
                "sha256": sha256_file(path),
            })
        elif stat.S_ISDIR(metadata.st_mode):
            rows.append({"path": relative, "type": "directory"})
        else:
            rows.append({"path": relative, "type": "special"})
    return rows


def v1_snapshot() -> dict[str, Any]:
    rows = inventory_tree(V1_ROOT)
    return {
        "entries": rows,
        "entry_count": len(rows),
        "file_count": sum(row["type"] == "file" for row in rows),
        "tree_sha256": sha256_bytes(canonical(rows)),
        "file_inventory_sha256": sha256_bytes(canonical([row for row in rows if row["type"] == "file"])),
    }


def count_tool_calls(events: list[dict[str, Any]]) -> int:
    tool_types = {
        "command_execution", "file_change", "mcp_tool_call", "web_search",
        "image_generation", "dynamic_tool_call", "tool_call", "function_call",
    }
    keys: set[str] = set()
    for event in events:
        if event.get("type") not in {"item.started", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") not in tool_types:
            continue
        identifier = item.get("id")
        keys.add("id:" + identifier if isinstance(identifier, str) else "item:" + sha256_bytes(canonical(item)))
    return len(keys)


def parse_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    errors = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(value, dict):
            events.append(value)
    return events, errors


def verify_v1() -> dict[str, Any]:
    snapshot = v1_snapshot()
    if snapshot["tree_sha256"] != V1_TREE_SHA256 or snapshot["file_count"] != V1_FILE_COUNT:
        raise ValueError("controlled_v3_construction_v1 changed before V2 amendment")
    attempt = V1_ROOT / "acquisitions/raw/X01/attempt-001"
    candidate = attempt / "workspace/candidate"
    if not candidate.is_dir() or any(candidate.iterdir()):
        raise ValueError("V1 X01 candidate directory is not exactly empty")
    events, parse_errors = parse_events(attempt / "record/events.jsonl")
    outcome = json.loads((attempt / "record/outcome.json").read_text(encoding="utf-8"))
    progress = json.loads((V1_ROOT / "progress.json").read_text(encoding="utf-8"))
    if parse_errors or count_tool_calls(events) != 0:
        raise ValueError("V1 raw event trajectory no longer establishes zero tool calls")
    if not any(event.get("type") == "turn.failed" for event in events):
        raise ValueError("V1 raw event trajectory no longer contains the model-unavailable failure")
    if outcome.get("machine_admitted") is not False or outcome.get("accepted_hashes") is not None:
        raise ValueError("V1 outcome unexpectedly contains an admitted candidate")
    if progress.get("evaluated_agent_outcomes") != 0 or progress.get("actual_v3_human_reviews") != 0:
        raise ValueError("V1 zero evaluation/review provenance changed")
    return {
        **snapshot,
        "x01_attempt_001_event_count": len(events),
        "x01_attempt_001_tool_calls": 0,
        "x01_candidate_artifact_count": 0,
        "x01_semantic_constructor_output_exists": False,
        "x01_machine_admissible_candidate_exists": False,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }


def selected_catalog_metadata() -> dict[str, Any]:
    probe = capture([str(CODEX), "debug", "models", "--bundled"], timeout=120)
    if probe["returncode"] != 0:
        raise ValueError("unable to read bundled Codex model catalog: " + probe["stderr"][:500])
    value = json.loads(probe["stdout"])
    rows = value if isinstance(value, list) else value.get("models", [])
    row = next((item for item in rows if item.get("slug") == MODEL_ID), None)
    if row is None:
        raise ValueError("selected Sol model is absent from bundled Codex catalog")
    supported = [item.get("effort") for item in row.get("supported_reasoning_levels", [])]
    if REASONING_EFFORT not in supported:
        raise ValueError("selected max reasoning effort is absent from bundled Codex catalog")
    keys = (
        "slug", "display_name", "description", "default_reasoning_level",
        "supported_reasoning_levels", "default_reasoning_summary", "default_verbosity",
        "context_window", "max_context_window", "effective_context_window_percent",
        "service_tiers", "additional_speed_tiers", "tool_mode", "shell_type",
        "use_responses_lite", "comp_hash", "supported_in_api",
    )
    return {
        "bundled_catalog_stdout_sha256": sha256_bytes(probe["stdout"].encode("utf-8")),
        "selected_entry": {key: row[key] for key in keys if key in row},
    }


def safe_user_config_observation() -> dict[str, Any]:
    raw = USER_CONFIG.read_bytes()
    value = tomllib.loads(raw.decode("utf-8"))
    relevant_keys = (
        "model", "model_reasoning_effort", "service_tier", "model_provider",
        "approval_policy", "sandbox_mode", "profile",
    )
    return {
        "path": str(USER_CONFIG),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "relevant_values": {key: value.get(key) for key in relevant_keys},
        "project_config_present": (REPO_ROOT / ".codex/config.toml").is_file(),
        "disposition": (
            "OBSERVED_BUT_NOT_AUTHORITATIVE_FOR_V2; explicit frozen CLI flags implement "
            "the project-owner-corrected Sol 5.6/max constructor runtime"
        ),
    }


def runtime_probes() -> dict[str, Any]:
    executable = CODEX.resolve()
    version = capture([str(CODEX), "--version"])
    login = capture([str(CODEX), "login", "status"])
    if version["returncode"] != 0 or version["stdout"].strip() != "codex-cli 0.153.3":
        raise ValueError("unexpected Codex CLI version")
    login_status = (login["stdout"] + login["stderr"]).strip()
    if login["returncode"] != 0 or login_status != "Logged in using ChatGPT":
        raise ValueError("Codex authentication mode is not ChatGPT")
    probe_root = V2_ROOT / "runtime_configuration_probes"
    write_new(probe_root / "codex_version.stdout", version["stdout"].encode("utf-8"))
    write_new(probe_root / "codex_version.stderr", version["stderr"].encode("utf-8"))
    write_new(probe_root / "login_status.stdout", login["stdout"].encode("utf-8"))
    write_new(probe_root / "login_status.stderr", login["stderr"].encode("utf-8"))
    return {
        "codex_cli_version": "0.153.3",
        "codex_version_output": version["stdout"].strip(),
        "executable_path": str(executable),
        "executable_sha256": sha256_file(executable),
        "authentication_mode": "ChatGPT",
        "authentication_status_output": login_status,
        "credentials_store_setting": None,
        "credentials_file_present": Path("/home/s224049759/.codex/auth.json").is_file(),
        "openai_api_key_environment_present": bool(os.environ.get("OPENAI_API_KEY")),
        "codex_api_key_environment_present": bool(os.environ.get("CODEX_API_KEY")),
    }


def inside_command() -> list[str]:
    return [
        "--ask-for-approval", "never",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--ephemeral",
        "--model", MODEL_ID,
        "--config", f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--config", f'service_tier="{SERVICE_TIER}"',
        "--sandbox", "workspace-write",
        "--cd", "/workspace",
        "--skip-git-repo-check",
        "--json",
        "--color", "never",
        "--output-last-message", "/workspace/final_message.txt",
        "-",
    ]


def run_dummy() -> dict[str, Any]:
    root = V2_ROOT / "runtime_accessibility_check"
    record = root / "record"
    workspace = root / "workspace"
    for name in ("inputs", "repository", "tools", "candidate", ".scratch"):
        (workspace / name).mkdir(parents=True, exist_ok=False)
    write_new(workspace / "AGENTS.md", DUMMY_AGENTS.encode("utf-8"))
    write_new(record / "prompt.txt", DUMMY_PROMPT.encode("utf-8"))
    inside = inside_command()
    started_at = utc_now()
    with tempfile.TemporaryDirectory(prefix="controlled-v3-v2-runtime-access-") as temporary:
        chroot_root = Path(temporary) / "root"
        v1_launcher.initialize_chroot(chroot_root)
        command = v1_launcher.isolated_command(chroot_root, workspace, inside)
        write_new_json(record / "invocation.json", {
            "schema_version": "controlled-v3-v2-runtime-accessibility-invocation/1",
            "started_at_utc": started_at,
            "benchmark_invocation": False,
            "x_family": None,
            "counts_as_constructor_attempt": False,
            "host_command": command,
            "inside_codex_command": ["codex", *inside],
            "prompt_sha256": sha256_bytes(DUMMY_PROMPT.encode("utf-8")),
            "workspace_agents_sha256": sha256_bytes(DUMMY_AGENTS.encode("utf-8")),
        })
        execution = v1_launcher.execute_codex(
            command,
            workspace=workspace,
            prompt=DUMMY_PROMPT.encode("utf-8"),
            events=record / "events.jsonl",
            stderr=record / "stderr.log",
            timeout_seconds=120,
        )
    events, parse_errors = parse_events(record / "events.jsonl")
    final_path = workspace / "final_message.txt"
    final_text = final_path.read_text(encoding="utf-8", errors="replace") if final_path.is_file() else ""
    errors = [event for event in events if event.get("type") in {"error", "turn.failed"}]
    tool_calls = count_tool_calls(events)
    success = (
        execution.get("returncode") == 0
        and execution.get("timed_out") is False
        and execution.get("tool_limit_exceeded") is False
        and parse_errors == 0
        and not errors
        and any(event.get("type") == "turn.completed" for event in events)
        and tool_calls == 0
        and final_text.strip() == DUMMY_ACK
    )
    result = {
        "schema_version": "controlled-v3-v2-runtime-accessibility-result/1",
        "completed_at_utc": utc_now(),
        "status": "PASS" if success else "FAIL",
        "configuration_accessible": success,
        "benchmark_invocation": False,
        "x_family": None,
        "counts_as_constructor_attempt": False,
        "event_count": len(events),
        "event_json_parse_errors": parse_errors,
        "tool_calls": tool_calls,
        "terminal_event_types": [event.get("type") for event in events if event.get("type") in {"turn.completed", "turn.failed"}],
        "error_events": errors,
        "final_message_sha256": sha256_bytes(final_text.encode("utf-8")),
        "final_message_exact_acknowledgment": final_text.strip() == DUMMY_ACK,
        "execution": execution,
        "raw_events_sha256": sha256_file(record / "events.jsonl"),
        "raw_stderr_sha256": sha256_file(record / "stderr.log"),
    }
    write_new_json(record / "result.json", result)
    if not success:
        raise RuntimeError("the single non-benchmark runtime accessibility invocation failed")
    return result


def write_readme() -> None:
    text = f"""# Controlled synthetic V3 construction V2 runtime amendment

Release ID: `{V2_RELEASE_ID}`.

This separately versioned, pre-construction amendment corrects only the constructor
runtime implementation binding. It does not alter any scientific specification,
the `{DIFFICULTY_RELEASE_ID}` release, evaluator envelope, validator, canonical
test, family order, X19/X25 exclusion, four-attempt cap, ceiling-risk metadata,
machine admission criterion, or human-review protocol.

Construction V1 remains byte-for-byte preserved as historical provenance. Its
X01 attempt-001 is classified `ABORTED_PRE_SEMANTIC_CONSTRUCTION_MODEL_UNAVAILABLE`:
the exact raw failed invocation remains present and is neither deleted nor
reinterpreted. It produced zero candidate artifacts, zero tool calls, no semantic
constructor output, no machine-admissible candidate, no evaluated-agent outcome,
and no human review. It does not consume any of V2's four attempts for X01.

The V2 constructor runtime is Codex CLI 0.153.3 authenticated through ChatGPT,
model `{MODEL_ID}`, reasoning effort `{REASONING_EFFORT}`, Fast Mode disabled,
and explicit standard service tier. The exact noninteractive command controls,
binary digest, sandbox, authentication probe, model-catalog projection, and
relevant configuration are recorded in `constructor_runtime_amendment.json`.

One empty-workspace, non-benchmark accessibility invocation was completed and its
raw JSONL events and stderr are preserved under `runtime_accessibility_check/`.
It is not an X-family constructor attempt. No X-family input was mounted.

At this freeze, every V2 in-scope family has zero attempts, evaluated-agent
outcomes are zero, and actual V3 human reviews are zero. Construction must stop
until this amendment is committed and its commit is recorded externally.
"""
    write_new(V2_ROOT / "README.md", text.encode("utf-8"))


def write_v1_disposition(v1: dict[str, Any]) -> None:
    write_new_json(V2_ROOT / "v1_abort_disposition.json", {
        "schema_version": "controlled-v3-construction-v1-abort-disposition/1",
        "construction_version": "controlled_v3_construction_v1",
        "status": "ABORTED_PRE_SEMANTIC_CONSTRUCTION_MODEL_UNAVAILABLE",
        "recorded_in": V2_RELEASE_ID,
        "historical_root": "synthetic_triplets/controlled_v3_construction_v1",
        "historical_tree_sha256": v1["tree_sha256"],
        "historical_file_inventory_sha256": v1["file_inventory_sha256"],
        "historical_entry_count": v1["entry_count"],
        "historical_file_count": v1["file_count"],
        "preserved_unchanged": True,
        "failed_invocation": "X01/attempt-001",
        "failed_invocation_retained_as_historical_provenance": True,
        "failed_invocation_reinterpreted": False,
        "failed_invocation_deleted": False,
        "x01_candidate_artifacts": 0,
        "x01_tool_calls": 0,
        "semantic_constructor_output_existed": False,
        "machine_admissible_candidate_existed": False,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
        "v1_infrastructure_invocation_count": 1,
        "v2_attempts_consumed_by_v1_invocation": 0,
        "v2_x01_attempts_remaining": 4,
        "reason": (
            "Construction V1 bound the generic frozen Codex runtime label to the "
            "deprecated gpt-5-codex model identifier. The provider rejected that "
            "identifier before a semantic model turn or any tool call."
        ),
    })


def write_runtime_configuration(
    probes: dict[str, Any], catalog: dict[str, Any], dummy: dict[str, Any],
) -> None:
    write_new_json(V2_ROOT / "constructor_runtime_amendment.json", {
        "schema_version": "controlled-v3-construction-v2-constructor-runtime-amendment/1",
        "release_id": V2_RELEASE_ID,
        "status": "FROZEN_PRE_X_FAMILY_CONSTRUCTION",
        "configuration_authority": (
            "Project-owner correction: the intended constructor is the active Codex "
            "agent/runtime, explicitly identified as Sol 5.6 at max reasoning."
        ),
        "constructor": {
            "runtime": "Codex agent via Codex CLI",
            "model_identifier": MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "fast_mode_enabled": FAST_MODE_ENABLED,
            "service_tier": SERVICE_TIER,
            "codex_cli_version": probes["codex_cli_version"],
            "codex_executable_path": probes["executable_path"],
            "codex_executable_sha256": probes["executable_sha256"],
            "authentication_mode": probes["authentication_mode"],
            "authentication_status": probes["authentication_status_output"],
            "model_provider": "openai",
            "wire_api": "responses",
            "approval_policy": "never",
            "sandbox_mode": "workspace-write",
            "sandbox_network_access": False,
            "noninteractive": True,
            "ephemeral_session": True,
            "ignore_user_config": True,
            "ignore_rules": True,
            "strict_config": True,
            "reasoning_summary_override": None,
            "verbosity_override": None,
            "timeout_seconds": TIMEOUT_SECONDS,
            "tool_call_limit": TOOL_CALL_LIMIT,
            "maximum_output_tokens": MAXIMUM_OUTPUT_TOKENS,
        },
        "exact_inside_command_prefix": ["codex", *inside_command()[:-1]],
        "prompt_transport": "stdin",
        "model_catalog": catalog,
        "authentication_probe": probes,
        "observed_user_config": safe_user_config_observation(),
        "dummy_accessibility": {
            "status": dummy["status"],
            "configuration_accessible": dummy["configuration_accessible"],
            "raw_events_sha256": dummy["raw_events_sha256"],
            "tool_calls": dummy["tool_calls"],
            "counts_as_constructor_attempt": False,
        },
        "configuration_change_after_x01_begins_permitted": False,
    })


def write_plan(dummy: dict[str, Any]) -> None:
    write_new_json(V2_ROOT / "construction_plan.json", {
        "schema_version": "controlled-v3-construction-v2-plan/1",
        "release_id": V2_RELEASE_ID,
        "status": "RUNTIME_FROZEN_CONSTRUCTION_NOT_STARTED",
        "base_freeze_commit": BASE_FREEZE_COMMIT,
        "difficulty_release_id": DIFFICULTY_RELEASE_ID,
        "difficulty_manifest_sha256": DIFFICULTY_MANIFEST_SHA256,
        "family_order": list(IN_SCOPE),
        "excluded_zero_attempts": {
            "X19": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED",
            "X25": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED",
        },
        "attempt_cap_per_family": 4,
        "v2_attempt_count_by_family": {family: 0 for family in IN_SCOPE},
        "total_v2_x_family_constructor_attempts": 0,
        "dummy_accessibility_invocations": 1,
        "dummy_accessibility_counts_as_x_family_attempt": False,
        "dummy_accessibility_status": dummy["status"],
        "first_machine_admissible_retained": True,
        "candidate_shopping_after_admission": False,
        "manual_repair": False,
        "prior_attempt_feedback": False,
        "continue_after_four_attempt_exhaustion": True,
        "constructor_configuration_change_after_x01": False,
        "ceiling_risk_metadata_affects_construction_or_admission": False,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
        "preserved_unchanged": [
            "all scientific specifications",
            DIFFICULTY_RELEASE_ID,
            "evaluator envelope",
            "validators and canonical tests",
            "X01-X28 order",
            "X19/X25 exclusions",
            "four-attempt cap",
            "ceiling-risk metadata",
            "admission criteria",
            "human-review protocol",
        ],
    })


def write_manifest() -> dict[str, Any]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(V2_ROOT.rglob("*")):
        if not path.is_file() or path.name in {"manifest.json", "commit_receipt.json"}:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        inventory[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {
        "schema_version": "controlled-v3-construction-v2-runtime-manifest/1",
        "release_id": V2_RELEASE_ID,
        "status": "FROZEN_PRE_X_FAMILY_CONSTRUCTION",
        "frozen_at_utc": utc_now(),
        "base_freeze_commit": BASE_FREEZE_COMMIT,
        "difficulty_release_id": DIFFICULTY_RELEASE_ID,
        "difficulty_manifest_sha256": DIFFICULTY_MANIFEST_SHA256,
        "v1_tree_sha256": V1_TREE_SHA256,
        "inventory": inventory,
        "exact_inventoried_file_count": len(inventory),
        "inventory_sha256": sha256_bytes(canonical(inventory)),
        "commit_receipt_exempt_from_inventory": True,
        "post_freeze_mutable_paths_exempt_from_inventory": [
            "synthetic_triplets/controlled_v3_construction_v2/acquisitions/",
            "synthetic_triplets/controlled_v3_construction_v2/construction_ledger.json",
            "synthetic_triplets/controlled_v3_construction_v2/construction_ledger.json.lock",
            "synthetic_triplets/controlled_v3_construction_v2/progress.json",
            "synthetic_triplets/controlled_v3_construction_v2/construction_report.json",
        ],
        "x_family_constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }
    write_new_json(V2_ROOT / "manifest.json", manifest)
    return manifest


def assert_base_state() -> None:
    if V2_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite V2 runtime amendment: {V2_ROOT}")
    head = capture(["git", "rev-parse", "HEAD"])
    if head["returncode"] or head["stdout"].strip() != BASE_FREEZE_COMMIT:
        raise ValueError("V2 runtime amendment must begin from the requested base freeze commit")
    tracked = capture(["git", "diff", "--quiet", "HEAD", "--", "."])
    if tracked["returncode"] != 0:
        raise ValueError("tracked files differ from the base freeze commit")
    difficulty_envelope.verify(REPO_ROOT, expected_manifest_sha256=DIFFICULTY_MANIFEST_SHA256)


def create() -> dict[str, Any]:
    assert_base_state()
    v1 = verify_v1()
    V2_ROOT.mkdir(parents=True)
    try:
        probes = runtime_probes()
        catalog = selected_catalog_metadata()
        dummy = run_dummy()
        write_readme()
        write_v1_disposition(v1)
        write_runtime_configuration(probes, catalog, dummy)
        write_plan(dummy)
        manifest = write_manifest()
    except BaseException:
        # Preserve any raw dummy trajectory already created. Never retry implicitly.
        raise
    after = verify_v1()
    if after["tree_sha256"] != v1["tree_sha256"]:
        raise ValueError("controlled_v3_construction_v1 changed during V2 amendment creation")
    return {
        "release_id": V2_RELEASE_ID,
        "status": manifest["status"],
        "manifest_sha256": sha256_file(V2_ROOT / "manifest.json"),
        "inventory_sha256": manifest["inventory_sha256"],
        "inventory_file_count": manifest["exact_inventoried_file_count"],
        "v1_tree_sha256": v1["tree_sha256"],
        "dummy_accessibility_status": dummy["status"],
        "v2_x_family_constructor_attempts": 0,
        "constructor": {
            "model_identifier": MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "fast_mode_enabled": FAST_MODE_ENABLED,
            "service_tier": SERVICE_TIER,
            "codex_cli_version": probes["codex_cli_version"],
            "authentication_mode": probes["authentication_mode"],
            "codex_executable_sha256": probes["executable_sha256"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    if not args.create:
        parser.error("specify --create")
    print(json.dumps(create(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
