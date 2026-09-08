#!/usr/bin/env python3
"""Finalize the V2 runtime amendment without another Codex invocation.

The single dummy trajectory already exists.  This pre-freeze finalizer preserves
it byte-for-byte, records its code-mode-host diagnostic, freezes the installed
companion executable and V2 launcher, and rebuilds the amendment manifest.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

from scripts import run_controlled_v3_pool as v1_launcher  # noqa: E402
from scripts import run_controlled_v3_pool_v2 as v2_launcher  # noqa: E402
from scripts import v3_difficulty_envelope as difficulty_envelope  # noqa: E402


BASE_FREEZE_COMMIT = "d2799394625e7ada8256daa4a1005e4c88b1e21a"
DIFFICULTY_MANIFEST_SHA256 = "e9076e48aa465c9a921da98fcd0accaefc957a84116ac4b0d6bbdc1c9e0e4403"
V1_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v1"
V1_TREE_SHA256 = "899f47535854e79060ec6a70ae12ca61f31b67d294e2f596de19034adacc2afb"
V2_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v2"
V2_RELEASE_ID = "controlled-v3-construction-v2-runtime-amendment-v1"
PRE_FINALIZATION_MANIFEST_SHA256 = "e2cd16a57b15bbe266e6c9c7ecf6d703717c36d370ad09dc28f3d617868fd93c"
PRE_FINALIZATION_INVENTORY_SHA256 = "d3ccea1de1a8e067ef863886ab0200afcb1d93c155ab91707e95f7dc49d3b3cd"
DUMMY_RAW_EVENTS_SHA256 = "59def1389c5dae6f3a7a81bb09d74366a31b643541077e7d365aefca6d28ab21"
DUMMY_ACK = "CONTROLLED_V3_CONSTRUCTION_V2_RUNTIME_ACCESS_OK"
MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "max"
SERVICE_TIER = "default"
CODEX = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex")
CODE_MODE_HOST = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex-code-mode-host")
CODEX_SHA256 = "f9d4eab23d0e0726340e084ed22d668885c1dcabeb29ec508b8962e5e29b8dc6"
CODE_MODE_HOST_SHA256 = "2a613d25c052bf570e19cdb2589857b0ba5429a2325e397e7ddba4ae36338faa"
V2_LAUNCHER_PATH = REPO_ROOT / "scripts/run_controlled_v3_pool_v2.py"

PROVENANCE_SCRIPTS = (
    "scripts/run_controlled_v3_pool.py",
    "scripts/freeze_controlled_v3_construction_v2.py",
    "scripts/finalize_controlled_v3_construction_v2.py",
    "scripts/verify_controlled_v3_construction_v2.py",
    "scripts/run_controlled_v3_pool_v2.py",
)
MUTABLE_PATHS = (
    "synthetic_triplets/controlled_v3_construction_v2/acquisitions/",
    "synthetic_triplets/controlled_v3_construction_v2/launcher_control_freeze.json",
    "synthetic_triplets/controlled_v3_construction_v2/construction_ledger.json",
    "synthetic_triplets/controlled_v3_construction_v2/construction_ledger.json.lock",
    "synthetic_triplets/controlled_v3_construction_v2/progress.json",
    "synthetic_triplets/controlled_v3_construction_v2/construction_report.json",
)


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def write_new_json(path: Path, value: object) -> None:
    write_new(path, json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def replace_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".pre-freeze-finalize.tmp")
    if temporary.exists():
        raise FileExistsError(temporary)
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


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


def capture(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def verify_preconditions() -> dict[str, Any]:
    if not V2_ROOT.is_dir() or (V2_ROOT / "commit_receipt.json").exists():
        raise ValueError("V2 must exist and remain uncommitted/unreceipted for finalization")
    head = capture(["git", "rev-parse", "HEAD"])
    if head.returncode or head.stdout.decode().strip() != BASE_FREEZE_COMMIT:
        raise ValueError("pre-freeze finalization requires the exact scientific base commit")
    if capture(["git", "diff", "--quiet", "HEAD", "--", "."]).returncode != 0:
        raise ValueError("tracked files differ from the scientific base commit")
    difficulty_envelope.verify(REPO_ROOT, expected_manifest_sha256=DIFFICULTY_MANIFEST_SHA256)
    v1_rows = inventory_tree(V1_ROOT)
    if sha256_bytes(canonical(v1_rows)) != V1_TREE_SHA256:
        raise ValueError("controlled_v3_construction_v1 changed")
    manifest_path = V2_ROOT / "manifest.json"
    if sha256_file(manifest_path) != PRE_FINALIZATION_MANIFEST_SHA256:
        raise ValueError("unexpected pre-finalization V2 manifest")
    manifest = read_json(manifest_path)
    if manifest.get("inventory_sha256") != PRE_FINALIZATION_INVENTORY_SHA256:
        raise ValueError("unexpected pre-finalization V2 inventory")
    if (V2_ROOT / "acquisitions").exists():
        raise ValueError("an X-family construction path exists before runtime freeze")
    return {"v1_rows": v1_rows, "manifest": manifest}


def verify_dummy() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    record = V2_ROOT / "runtime_accessibility_check/record"
    events_path = record / "events.jsonl"
    if sha256_file(events_path) != DUMMY_RAW_EVENTS_SHA256:
        raise ValueError("single dummy raw events changed")
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8", errors="strict").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("dummy event is not an object")
        events.append(value)
    result = read_json(record / "result.json")
    if len(events) != 5 or result.get("status") != "PASS" or result.get("tool_calls") != 0:
        raise ValueError("single dummy accessibility result changed")
    if (V2_ROOT / "runtime_accessibility_check/workspace/final_message.txt").read_text(encoding="utf-8").strip() != DUMMY_ACK:
        raise ValueError("single dummy acknowledgment changed")
    diagnostic_items = [
        event for event in events
        if event.get("type") in {"item.started", "item.completed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "error"
    ]
    if len(diagnostic_items) != 1:
        raise ValueError("expected exactly one preserved dummy diagnostic item")
    message = str(diagnostic_items[0]["item"].get("message", ""))
    if "Code Mode is unavailable" not in message or "host executable was not found" not in message:
        raise ValueError("unexpected dummy diagnostic text")
    return result, diagnostic_items


def verify_launcher() -> dict[str, Any]:
    if sha256_file(CODEX) != CODEX_SHA256 or sha256_file(CODE_MODE_HOST) != CODE_MODE_HOST_SHA256:
        raise ValueError("installed Codex runtime binaries differ from the observed 0.153.3 release")
    if v2_launcher.PROMPT_TEMPLATE != v1_launcher.PROMPT_TEMPLATE:
        raise ValueError("V2 launcher changed the constructor prompt")
    if v2_launcher.WORKSPACE_AGENTS != v1_launcher.WORKSPACE_AGENTS:
        raise ValueError("V2 launcher changed the workspace instructions")
    if v2_launcher.PUBLIC_CHECK_TOOL != v1_launcher.PUBLIC_CHECK_TOOL:
        raise ValueError("V2 launcher changed the public-check wrapper")
    if tuple(v2_launcher.IN_SCOPE) != tuple(v1_launcher.IN_SCOPE):
        raise ValueError("V2 launcher changed family order or scope")
    if tuple(v2_launcher.EXCLUDED) != tuple(v1_launcher.EXCLUDED):
        raise ValueError("V2 launcher changed exclusions")
    if v2_launcher.RISK_LABELS != v1_launcher.RISK_LABELS:
        raise ValueError("V2 launcher changed ceiling-risk metadata")
    expected_inside = [
        "--ask-for-approval", "never", "exec", "--ignore-user-config", "--ignore-rules",
        "--strict-config", "--ephemeral", "--model", MODEL_ID,
        "--config", 'model_reasoning_effort="max"',
        "--config", 'service_tier="default"',
        "--sandbox", "workspace-write", "--cd", "/workspace", "--skip-git-repo-check",
        "--json", "--color", "never", "--output-last-message", "/workspace/final_message.txt", "-",
    ]
    if v2_launcher.inside_codex_command("/workspace/final_message.txt") != expected_inside:
        raise ValueError("V2 launcher command differs from the accessible Sol/max command")
    if '"$root/codex/codex-code-mode-host"' not in v2_launcher.CHROOT_SCRIPT:
        raise ValueError("V2 launcher does not bind the code-mode host into isolation")
    if v2_launcher.RESULT_ROOT != Path("synthetic_triplets/controlled_v3_construction_v2"):
        raise ValueError("V2 launcher output namespace differs")
    if v2_launcher.CLI_MODEL != MODEL_ID or v2_launcher.REASONING_EFFORT != REASONING_EFFORT:
        raise ValueError("V2 launcher model configuration differs")
    if v2_launcher.SERVICE_TIER != SERVICE_TIER or v2_launcher.FAST_MODE_ENABLED is not False:
        raise ValueError("V2 launcher speed configuration differs")
    return {
        "path": V2_LAUNCHER_PATH.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_file(V2_LAUNCHER_PATH),
        "constructor_prompt_sha256": sha256_bytes(v2_launcher.PROMPT_TEMPLATE.encode("utf-8")),
        "workspace_instructions_sha256": sha256_bytes(v2_launcher.WORKSPACE_AGENTS.encode("utf-8")),
        "public_check_wrapper_sha256": sha256_bytes(v2_launcher.PUBLIC_CHECK_TOOL.encode("utf-8")),
        "inside_command": ["codex", *expected_inside],
        "code_mode_host_bind_target": "/codex/codex-code-mode-host",
    }


def preserve_host_probe() -> dict[str, Any]:
    probe = capture([str(CODE_MODE_HOST), "--help"])
    root = V2_ROOT / "runtime_configuration_probes"
    write_new(root / "code_mode_host_help.stdout", probe.stdout)
    write_new(root / "code_mode_host_help.stderr", probe.stderr)
    status = probe.returncode == 0 and b"Usage: codex-code-mode-host" in probe.stdout
    value = {
        "schema_version": "controlled-v3-v2-code-mode-host-static-probe/1",
        "recorded_at_utc": utc_now(),
        "constructor_invocation": False,
        "benchmark_invocation": False,
        "x_family": None,
        "counts_as_constructor_attempt": False,
        "command": [str(CODE_MODE_HOST), "--help"],
        "returncode": probe.returncode,
        "status": "PASS" if status else "FAIL",
        "stdout_sha256": sha256_bytes(probe.stdout),
        "stderr_sha256": sha256_bytes(probe.stderr),
        "code_mode_host_sha256": sha256_file(CODE_MODE_HOST),
    }
    write_new_json(root / "code_mode_host_probe.json", value)
    if not status:
        raise RuntimeError("installed Codex code-mode host static probe failed")
    return value


def write_diagnostic_disposition(
    diagnostic_items: list[dict[str, Any]], launcher: dict[str, Any], host_probe: dict[str, Any],
) -> dict[str, Any]:
    value = {
        "schema_version": "controlled-v3-v2-dummy-diagnostic-disposition/1",
        "status": "RECORDED_WITH_PRE_X01_COMPANION_BINDING",
        "raw_dummy_events_preserved_unchanged": True,
        "raw_dummy_events_sha256": DUMMY_RAW_EVENTS_SHA256,
        "diagnostic_item_count": len(diagnostic_items),
        "diagnostic_items": diagnostic_items,
        "diagnostic_category": "DUMMY_ISOLATION_CODE_MODE_HOST_NOT_MOUNTED",
        "dummy_model_accessibility": "PASS",
        "dummy_prompt_prohibited_tool_calls": True,
        "dummy_tool_calls": 0,
        "dummy_assessed_artifact_tooling": False,
        "second_dummy_invocation_performed": False,
        "total_dummy_constructor_invocations": 1,
        "x_family_constructor_attempts": 0,
        "pre_x01_runtime_binding": {
            "launcher_path": launcher["path"],
            "launcher_sha256": launcher["sha256"],
            "code_mode_host_path": str(CODE_MODE_HOST),
            "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
            "code_mode_host_bind_target": launcher["code_mode_host_bind_target"],
            "static_host_probe_status": host_probe["status"],
            "end_to_end_tool_call_probe_performed": False,
        },
    }
    write_new_json(V2_ROOT / "runtime_accessibility_check/record/diagnostic_disposition.json", value)
    return value


def update_runtime_configuration(
    launcher: dict[str, Any], host_probe: dict[str, Any], disposition: dict[str, Any],
) -> None:
    path = V2_ROOT / "constructor_runtime_amendment.json"
    original_sha256 = sha256_file(path)
    value = read_json(path)
    constructor = value["constructor"]
    constructor.update({
        "code_mode_host_required": True,
        "code_mode_host_path": str(CODE_MODE_HOST),
        "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
        "code_mode_host_bind_target": launcher["code_mode_host_bind_target"],
        "constructor_launcher_path": launcher["path"],
        "constructor_launcher_sha256": launcher["sha256"],
    })
    value["constructor_launcher"] = launcher
    value["dummy_accessibility"].update({
        "scope": "model/configuration/authentication semantic accessibility; dummy prompt prohibited tools",
        "diagnostic_item_count": disposition["diagnostic_item_count"],
        "diagnostic_disposition_path": (
            "synthetic_triplets/controlled_v3_construction_v2/"
            "runtime_accessibility_check/record/diagnostic_disposition.json"
        ),
        "artifact_tooling_assessed_by_dummy": False,
        "second_dummy_invocation_performed": False,
        "total_dummy_constructor_invocations": 1,
    })
    value["code_mode_host_static_probe"] = host_probe
    value["pre_freeze_finalization"] = {
        "constructor_model_configuration_changed_after_dummy": False,
        "dummy_raw_events_changed": False,
        "pre_finalization_runtime_configuration_sha256": original_sha256,
        "companion_binding_added_before_x01": True,
    }
    replace_json(path, value)


def update_plan(host_probe: dict[str, Any], disposition: dict[str, Any]) -> None:
    path = V2_ROOT / "construction_plan.json"
    value = read_json(path)
    value.update({
        "dummy_diagnostic_item_count": disposition["diagnostic_item_count"],
        "dummy_artifact_tooling_assessed": False,
        "second_dummy_invocation_performed": False,
        "code_mode_host_static_probe_status": host_probe["status"],
        "code_mode_host_bound_by_frozen_v2_launcher": True,
    })
    replace_json(path, value)


def update_readme() -> None:
    path = V2_ROOT / "README.md"
    original = path.read_text(encoding="utf-8")
    section = """

The preserved dummy stream contains one nonfatal diagnostic: its historical
isolation mounted the main CLI executable but not the installed code-mode-host
companion. The dummy prompt prohibited tools, made zero tool calls, and still
completed the exact semantic acknowledgment. Before X01, V2 freezes a separate
launcher that binds the matching companion executable by exact SHA-256. A
non-model `--help` probe of that companion is preserved. In accordance with the
one-dummy requirement, no second Codex dummy or end-to-end tool-call probe was
performed; the original raw stream is unchanged and the diagnostic disposition
is explicit.
"""
    if "The preserved dummy stream contains one nonfatal diagnostic" in original:
        raise ValueError("README diagnostic section already exists")
    temporary = path.with_name(path.name + ".pre-freeze-finalize.tmp")
    temporary.write_text(original.rstrip() + section, encoding="utf-8")
    os.replace(temporary, path)


def build_inventory() -> dict[str, dict[str, Any]]:
    paths = [
        path for path in V2_ROOT.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "commit_receipt.json"}
    ]
    paths.extend(REPO_ROOT / relative for relative in PROVENANCE_SCRIPTS)
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(set(paths), key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix()
        inventory[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return inventory


def finalize() -> dict[str, Any]:
    pre = verify_preconditions()
    dummy, diagnostic_items = verify_dummy()
    launcher = verify_launcher()
    host_probe = preserve_host_probe()
    disposition = write_diagnostic_disposition(diagnostic_items, launcher, host_probe)
    update_runtime_configuration(launcher, host_probe, disposition)
    update_plan(host_probe, disposition)
    update_readme()
    if sha256_file(V2_ROOT / "runtime_accessibility_check/record/events.jsonl") != DUMMY_RAW_EVENTS_SHA256:
        raise ValueError("dummy raw events changed during pre-freeze finalization")
    if sha256_bytes(canonical(inventory_tree(V1_ROOT))) != V1_TREE_SHA256:
        raise ValueError("V1 changed during pre-freeze finalization")
    inventory = build_inventory()
    manifest = {
        "schema_version": "controlled-v3-construction-v2-runtime-manifest/2",
        "release_id": V2_RELEASE_ID,
        "status": "FROZEN_PRE_X_FAMILY_CONSTRUCTION",
        "frozen_at_utc": utc_now(),
        "base_freeze_commit": BASE_FREEZE_COMMIT,
        "difficulty_release_id": "controlled-synthetic-v3-difficulty-amendment-v1",
        "difficulty_manifest_sha256": DIFFICULTY_MANIFEST_SHA256,
        "v1_tree_sha256": V1_TREE_SHA256,
        "pre_finalization_manifest_sha256": PRE_FINALIZATION_MANIFEST_SHA256,
        "pre_finalization_inventory_sha256": PRE_FINALIZATION_INVENTORY_SHA256,
        "dummy_accessibility_status": dummy["status"],
        "dummy_accessibility_invocations": 1,
        "dummy_raw_events_sha256": DUMMY_RAW_EVENTS_SHA256,
        "dummy_diagnostic_item_count": len(diagnostic_items),
        "second_dummy_invocation_performed": False,
        "constructor_launcher_path": launcher["path"],
        "constructor_launcher_sha256": launcher["sha256"],
        "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
        "code_mode_host_static_probe_status": host_probe["status"],
        "inventory": inventory,
        "exact_inventoried_file_count": len(inventory),
        "inventory_sha256": sha256_bytes(canonical(inventory)),
        "commit_receipt_exempt_from_inventory": True,
        "post_freeze_mutable_paths_exempt_from_inventory": list(MUTABLE_PATHS),
        "x_family_constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }
    replace_json(V2_ROOT / "manifest.json", manifest)
    return {
        "release_id": V2_RELEASE_ID,
        "status": manifest["status"],
        "manifest_sha256": sha256_file(V2_ROOT / "manifest.json"),
        "inventory_sha256": manifest["inventory_sha256"],
        "inventory_file_count": manifest["exact_inventoried_file_count"],
        "v1_tree_sha256": V1_TREE_SHA256,
        "dummy_accessibility_status": dummy["status"],
        "dummy_diagnostic_item_count": len(diagnostic_items),
        "second_dummy_invocation_performed": False,
        "code_mode_host_static_probe_status": host_probe["status"],
        "constructor_launcher_sha256": launcher["sha256"],
        "v2_x_family_constructor_attempts": 0,
    }


def main() -> int:
    print(json.dumps(finalize(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
