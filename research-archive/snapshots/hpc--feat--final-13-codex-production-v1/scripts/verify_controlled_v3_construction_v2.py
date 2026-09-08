#!/usr/bin/env python3
"""Verify the frozen runtime amendment for controlled V3 construction V2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import v3_difficulty_envelope as difficulty_envelope  # noqa: E402


BASE_FREEZE_COMMIT = "d2799394625e7ada8256daa4a1005e4c88b1e21a"
DIFFICULTY_MANIFEST_SHA256 = "e9076e48aa465c9a921da98fcd0accaefc957a84116ac4b0d6bbdc1c9e0e4403"
V1_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v1"
V1_TREE_SHA256 = "899f47535854e79060ec6a70ae12ca61f31b67d294e2f596de19034adacc2afb"
V2_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v2"
MANIFEST_PATH = V2_ROOT / "manifest.json"
RELEASE_ID = "controlled-v3-construction-v2-runtime-amendment-v1"
MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "max"
SERVICE_TIER = "default"
DUMMY_ACK = "CONTROLLED_V3_CONSTRUCTION_V2_RUNTIME_ACCESS_OK"
CODEX = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex")
CODE_MODE_HOST = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex-code-mode-host")
CODEX_SHA256 = "f9d4eab23d0e0726340e084ed22d668885c1dcabeb29ec508b8962e5e29b8dc6"
CODE_MODE_HOST_SHA256 = "2a613d25c052bf570e19cdb2589857b0ba5429a2325e397e7ddba4ae36338faa"
DUMMY_RAW_EVENTS_SHA256 = "59def1389c5dae6f3a7a81bb09d74366a31b643541077e7d365aefca6d28ab21"
V2_LAUNCHER_PATH = "scripts/run_controlled_v3_pool_v2.py"
IN_SCOPE = (
    "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08", "X09",
    "X10", "X11", "X12", "X13", "X14", "X15", "X16", "X17", "X18",
    "X20", "X21", "X22", "X23", "X24", "X26", "X27", "X28",
)


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


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


def verify_v1() -> dict[str, Any]:
    rows = inventory_tree(V1_ROOT)
    digest = sha256_bytes(canonical(rows))
    if digest != V1_TREE_SHA256:
        raise ValueError("controlled_v3_construction_v1 differs from its recorded historical tree")
    attempt = V1_ROOT / "acquisitions/raw/X01/attempt-001"
    candidate = attempt / "workspace/candidate"
    if not candidate.is_dir() or any(candidate.iterdir()):
        raise ValueError("V1 X01 candidate artifacts are not exactly zero")
    events = [json.loads(line) for line in (attempt / "record/events.jsonl").read_text().splitlines()]
    tool_types = {
        "command_execution", "file_change", "mcp_tool_call", "web_search",
        "image_generation", "dynamic_tool_call", "tool_call", "function_call",
    }
    tool_items = {
        (event.get("item") or {}).get("id")
        for event in events
        if event.get("type") in {"item.started", "item.completed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") in tool_types
    }
    if tool_items:
        raise ValueError("V1 X01 no longer records zero tool calls")
    disposition = read_json(V2_ROOT / "v1_abort_disposition.json")
    required = {
        "status": "ABORTED_PRE_SEMANTIC_CONSTRUCTION_MODEL_UNAVAILABLE",
        "preserved_unchanged": True,
        "failed_invocation_reinterpreted": False,
        "failed_invocation_deleted": False,
        "x01_candidate_artifacts": 0,
        "x01_tool_calls": 0,
        "semantic_constructor_output_existed": False,
        "machine_admissible_candidate_existed": False,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
        "v2_attempts_consumed_by_v1_invocation": 0,
        "v2_x01_attempts_remaining": 4,
    }
    if any(disposition.get(key) != value for key, value in required.items()):
        raise ValueError("V1 abort disposition differs from the required provenance")
    return {"tree_sha256": digest, "entry_count": len(rows), "tool_calls": 0, "candidate_artifacts": 0}


def verify_manifest() -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    if manifest.get("release_id") != RELEASE_ID or manifest.get("status") != "FROZEN_PRE_X_FAMILY_CONSTRUCTION":
        raise ValueError("wrong V2 runtime-amendment identity/status")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict) or len(inventory) != manifest.get("exact_inventoried_file_count"):
        raise ValueError("malformed V2 runtime-amendment inventory")
    if sha256_bytes(canonical(inventory)) != manifest.get("inventory_sha256"):
        raise ValueError("V2 runtime-amendment inventory digest differs")
    for relative, metadata in inventory.items():
        path = REPO_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing/nonregular V2 frozen member: " + relative)
        observed = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        if observed != metadata:
            raise ValueError("changed V2 frozen member: " + relative)
    exempt_files = {"manifest.json", "commit_receipt.json"}
    mutable = tuple(manifest.get("post_freeze_mutable_paths_exempt_from_inventory", []))
    for path in V2_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_repo = path.relative_to(REPO_ROOT).as_posix()
        relative_v2 = path.relative_to(V2_ROOT).as_posix()
        if relative_repo in inventory or relative_v2 in exempt_files:
            continue
        if any(relative_repo == prefix.rstrip("/") or relative_repo.startswith(prefix) for prefix in mutable):
            continue
        raise ValueError("unexpected file in frozen V2 namespace: " + relative_repo)
    return manifest


def verify_runtime() -> dict[str, Any]:
    value = read_json(V2_ROOT / "constructor_runtime_amendment.json")
    constructor = value.get("constructor", {})
    expected = {
        "model_identifier": MODEL_ID,
        "reasoning_effort": REASONING_EFFORT,
        "fast_mode_enabled": False,
        "service_tier": SERVICE_TIER,
        "codex_cli_version": "0.153.3",
        "authentication_mode": "ChatGPT",
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
        "timeout_seconds": 600,
        "tool_call_limit": 60,
        "maximum_output_tokens": 16384,
        "code_mode_host_required": True,
        "code_mode_host_path": str(CODE_MODE_HOST),
        "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
        "code_mode_host_bind_target": "/codex/codex-code-mode-host",
        "constructor_launcher_path": V2_LAUNCHER_PATH,
    }
    if any(constructor.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValueError("frozen V2 constructor runtime differs")
    if value.get("configuration_change_after_x01_begins_permitted") is not False:
        raise ValueError("V2 constructor runtime is not immutable after X01")
    if constructor.get("codex_executable_sha256") != CODEX_SHA256:
        raise ValueError("V2 Codex executable digest differs")
    if sha256_file(CODEX) != CODEX_SHA256 or sha256_file(CODE_MODE_HOST) != CODE_MODE_HOST_SHA256:
        raise ValueError("installed V2 constructor binaries differ from the freeze")
    launcher = value.get("constructor_launcher", {})
    if launcher.get("path") != V2_LAUNCHER_PATH:
        raise ValueError("V2 constructor launcher path differs")
    if launcher.get("sha256") != sha256_file(REPO_ROOT / V2_LAUNCHER_PATH):
        raise ValueError("V2 constructor launcher digest differs")
    return value


def verify_dummy() -> dict[str, Any]:
    root = V2_ROOT / "runtime_accessibility_check"
    result = read_json(root / "record/result.json")
    if any((
        result.get("status") != "PASS",
        result.get("configuration_accessible") is not True,
        result.get("benchmark_invocation") is not False,
        result.get("x_family") is not None,
        result.get("counts_as_constructor_attempt") is not False,
        result.get("tool_calls") != 0,
        result.get("final_message_exact_acknowledgment") is not True,
    )):
        raise ValueError("dummy accessibility result is not the frozen passing non-benchmark check")
    if sha256_file(root / "record/events.jsonl") != result.get("raw_events_sha256"):
        raise ValueError("dummy raw event trajectory changed")
    if result.get("raw_events_sha256") != DUMMY_RAW_EVENTS_SHA256:
        raise ValueError("dummy raw event trajectory is not the single observed invocation")
    if sha256_file(root / "record/stderr.log") != result.get("raw_stderr_sha256"):
        raise ValueError("dummy raw stderr changed")
    final = (root / "workspace/final_message.txt").read_text(encoding="utf-8").strip()
    if final != DUMMY_ACK:
        raise ValueError("dummy final acknowledgment changed")
    events = [json.loads(line) for line in (root / "record/events.jsonl").read_text().splitlines()]
    diagnostics = [
        event for event in events
        if event.get("type") in {"item.started", "item.completed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "error"
    ]
    if len(diagnostics) != 1 or "Code Mode is unavailable" not in diagnostics[0]["item"].get("message", ""):
        raise ValueError("preserved dummy code-mode diagnostic differs")
    disposition = read_json(root / "record/diagnostic_disposition.json")
    required_disposition = {
        "status": "RECORDED_WITH_PRE_X01_COMPANION_BINDING",
        "raw_dummy_events_preserved_unchanged": True,
        "diagnostic_item_count": 1,
        "dummy_model_accessibility": "PASS",
        "dummy_tool_calls": 0,
        "dummy_assessed_artifact_tooling": False,
        "second_dummy_invocation_performed": False,
        "total_dummy_constructor_invocations": 1,
        "x_family_constructor_attempts": 0,
    }
    if any(disposition.get(key) != value for key, value in required_disposition.items()):
        raise ValueError("dummy diagnostic disposition differs")
    host_probe = read_json(V2_ROOT / "runtime_configuration_probes/code_mode_host_probe.json")
    if host_probe.get("status") != "PASS" or host_probe.get("constructor_invocation") is not False:
        raise ValueError("code-mode host static probe differs")
    return result


def verify_plan() -> dict[str, Any]:
    plan = read_json(V2_ROOT / "construction_plan.json")
    if plan.get("status") != "RUNTIME_FROZEN_CONSTRUCTION_NOT_STARTED":
        raise ValueError("V2 plan is not frozen before X-family construction")
    if tuple(plan.get("family_order", [])) != IN_SCOPE:
        raise ValueError("V2 family order differs")
    if plan.get("attempt_cap_per_family") != 4:
        raise ValueError("V2 attempt cap differs")
    if set(plan.get("excluded_zero_attempts", {})) != {"X19", "X25"}:
        raise ValueError("V2 exclusions differ")
    if any(plan.get(key) != 0 for key in (
        "total_v2_x_family_constructor_attempts", "evaluated_agent_outcomes", "actual_v3_human_reviews",
    )):
        raise ValueError("V2 pre-construction counters are not zero")
    if any(value != 0 for value in plan.get("v2_attempt_count_by_family", {}).values()):
        raise ValueError("a V2 family attempt exists in the frozen plan")
    if plan.get("second_dummy_invocation_performed") is not False:
        raise ValueError("V2 plan records more than the single dummy")
    if plan.get("code_mode_host_static_probe_status") != "PASS":
        raise ValueError("V2 plan lacks the code-mode host static probe")
    return plan


def verify_git_base() -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_FREEZE_COMMIT, "HEAD"],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("requested scientific freeze commit is not an ancestor")


def verify() -> dict[str, Any]:
    verify_git_base()
    difficulty_envelope.verify(REPO_ROOT, expected_manifest_sha256=DIFFICULTY_MANIFEST_SHA256)
    v1 = verify_v1()
    manifest = verify_manifest()
    runtime = verify_runtime()
    dummy = verify_dummy()
    plan = verify_plan()
    receipt_path = V2_ROOT / "commit_receipt.json"
    receipt = read_json(receipt_path) if receipt_path.is_file() else None
    if receipt is not None:
        recorded_manifest = receipt.get("runtime_manifest_sha256", receipt.get("manifest_sha256"))
        if recorded_manifest != sha256_file(MANIFEST_PATH):
            raise ValueError("V2 commit receipt is not bound to this manifest")
        if receipt.get("status") != "COMMITTED_PRE_X_FAMILY_CONSTRUCTION":
            raise ValueError("V2 commit receipt status differs")
        commit = receipt.get("freeze_commit")
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0:
            raise ValueError("V2 receipt freeze commit is unavailable")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if ancestor.returncode != 0:
            raise ValueError("V2 receipt freeze commit is not an ancestor")
        blob = subprocess.run(
            ["git", "show", f"{commit}:synthetic_triplets/controlled_v3_construction_v2/manifest.json"],
            cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if blob.returncode != 0 or blob.stdout != MANIFEST_PATH.read_bytes():
            raise ValueError("V2 receipt commit does not contain this manifest")
    return {
        "release_id": RELEASE_ID,
        "status": "VERIFIED",
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "inventory_sha256": manifest["inventory_sha256"],
        "inventory_file_count": manifest["exact_inventoried_file_count"],
        "v1": v1,
        "constructor": {
            key: runtime["constructor"][key]
            for key in (
                "model_identifier", "reasoning_effort", "fast_mode_enabled", "service_tier",
                "codex_cli_version", "codex_executable_sha256", "authentication_mode",
                "code_mode_host_sha256", "constructor_launcher_sha256",
            )
        },
        "dummy_accessibility_status": dummy["status"],
        "dummy_diagnostic_item_count": manifest["dummy_diagnostic_item_count"],
        "second_dummy_invocation_performed": manifest["second_dummy_invocation_performed"],
        "code_mode_host_static_probe_status": manifest["code_mode_host_static_probe_status"],
        "v2_x_family_constructor_attempts": plan["total_v2_x_family_constructor_attempts"],
        "evaluated_agent_outcomes": plan["evaluated_agent_outcomes"],
        "actual_v3_human_reviews": plan["actual_v3_human_reviews"],
        "commit_receipt_present": receipt is not None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("specify --verify")
    print(json.dumps(verify(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
