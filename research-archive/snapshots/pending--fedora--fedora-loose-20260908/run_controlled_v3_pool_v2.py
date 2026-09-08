#!/usr/bin/env python3
"""Post-freeze, append-only constructor launcher for controlled synthetic V3.

This launcher is intentionally outside every frozen release inventory.  It
materializes only the constructor inputs named by the difficulty-amendment
binding, preserves each raw Codex trajectory, and delegates candidate admission
unchanged to the frozen difficulty-amendment validator.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import v3_difficulty_envelope as envelope  # noqa: E402
from synthetic_triplets.controlled_v3_difficulty_amendment_v1 import validator  # noqa: E402
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import candidate_control as control  # noqa: E402


FREEZE_COMMIT = "d2799394625e7ada8256daa4a1005e4c88b1e21a"
RELEASE_ID = "controlled-synthetic-v3-difficulty-amendment-v1"
EXPECTED_MANIFEST_SHA256 = "e9076e48aa465c9a921da98fcd0accaefc957a84116ac4b0d6bbdc1c9e0e4403"
MANIFEST_PATH = Path("protocols") / RELEASE_ID / "manifest.json"
BINDINGS_PATH = Path("protocols") / RELEASE_ID / "constructor_input_bindings.json"
RISK_PATH = Path("protocols") / RELEASE_ID / "ceiling_risk_metadata.json"
CONSTRUCTOR_RELEASE_PATH = Path("synthetic_triplets/controlled_v3_expansion/construction_input_release.json")
PRODUCTION_LEDGER_PATH = Path("synthetic_triplets/controlled_v3_executable_oracle_release_v1/admission_ledger.json")

RESULT_ROOT = Path("synthetic_triplets/controlled_v3_construction_v2")
RAW_ROOT = RESULT_ROOT / "acquisitions" / "raw"
CONTROL_FREEZE_PATH = RESULT_ROOT / "launcher_control_freeze.json"
WORKING_LEDGER_PATH = RESULT_ROOT / "construction_ledger.json"
FINAL_REPORT_PATH = RESULT_ROOT / "construction_report.json"
PROGRESS_PATH = RESULT_ROOT / "progress.json"
RUNTIME_MANIFEST_PATH = RESULT_ROOT / "manifest.json"
RUNTIME_RECEIPT_PATH = RESULT_ROOT / "commit_receipt.json"
RUNTIME_CONFIGURATION_PATH = RESULT_ROOT / "constructor_runtime_amendment.json"
V1_ROOT = Path("synthetic_triplets/controlled_v3_construction_v1")
V1_TREE_SHA256 = "899f47535854e79060ec6a70ae12ca61f31b67d294e2f596de19034adacc2afb"
RUNTIME_RELEASE_ID = "controlled-v3-construction-v2-runtime-amendment-v1"

CODEX = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex")
CODE_MODE_HOST = Path("/home/s224049759/.codex/packages/standalone/releases/0.153.3-x86_64-unknown-linux-musl/bin/codex-code-mode-host")
CODEX_CLI_VERSION = "0.153.3"
CODEX_SHA256 = "f9d4eab23d0e0726340e084ed22d668885c1dcabeb29ec508b8962e5e29b8dc6"
CODE_MODE_HOST_SHA256 = "2a613d25c052bf570e19cdb2589857b0ba5429a2325e397e7ddba4ae36338faa"
CLI_MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "max"
SERVICE_TIER = "default"
FAST_MODE_ENABLED = False
FROZEN_MODEL = "Codex"
FROZEN_VERSION = "GPT-5 Codex runtime / 2026-09-05"
TIMEOUT_SECONDS = 600
TOOL_CALL_LIMIT = 60
MAXIMUM_OUTPUT_TOKENS = 16_384
POST_TERMINAL_GRACE_SECONDS = 15.0

IN_SCOPE = (
    "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08", "X09",
    "X10", "X11", "X12", "X13", "X14", "X15", "X16", "X17", "X18",
    "X20", "X21", "X22", "X23", "X24", "X26", "X27", "X28",
)
EXCLUDED = ("X19", "X25")
RISK_LABELS = {
    "LOW": ("X02",),
    "MEDIUM": (
        "X01", "X03", "X05", "X06", "X08", "X09", "X10", "X11",
        "X12", "X15", "X17", "X18", "X24",
    ),
    "HIGH": (
        "X04", "X07", "X13", "X14", "X16", "X20", "X21", "X22",
        "X23", "X26", "X27", "X28",
    ),
}


PROMPT_TEMPLATE = """You are the constructor for one prospectively frozen controlled-synthetic V3 family.

Work only from the visible files in this isolated workspace. Read `inputs/task.json`, the single file under `inputs/source/`, and the read-only `repository/`. The scientific task and the public repository are authoritative. Do not access the network, parent directories, Git metadata, other families, prior attempts, researcher tests, reference states, sealed witnesses, validator material, evaluated-agent outcomes, human-review judgments, or ceiling-risk metadata.

Create exactly the candidate artifacts listed in `inputs/task.json`, under `candidate/`:

* `candidate/B/<service path>` is the baseline/source procedure adapted to the target repository API. It must preserve existing behavior, lack the requested target feature, and remain valid under the source condition.
* `candidate/feature.patch` is a canonical unified Git patch that changes exactly that service path. Applied to B, it must implement the requested feature by direct procedural transfer while retaining the source applicability assumption; this is U.
* `candidate/security.patch` is a canonical unified Git patch that changes exactly that service path. Applied after `feature.patch`, it must implement the task's secure adaptation and full target security obligations while retaining existing and feature behavior; this is R.

Both patches must use `diff --git a/<service path> b/<service path>`, `--- a/<service path>`, `+++ b/<service path>`, contain textual hunks, apply sequentially with `git apply --no-index --whitespace=error-all`, and produce three distinct service files. The candidate directory may contain only `B/`, `feature.patch`, and `security.patch`; B may contain only its `app/` directory and service file. Candidate files must be UTF-8, non-executable, contain no NUL bytes, and remain within the frozen size limits. Do not place tests, notes, metadata, or scratch files in `candidate/`.

You may use `.scratch/` for temporary work and `python tools/run_public.py --service PATH` to run the two exact frozen public entrypoints against a Python or X02 service. The public tool is advisory; the external frozen validator alone decides machine admission. Do not modify `inputs/`, `repository/`, `tools/`, or this instruction file. Do not fabricate review or evaluation records. Finish after the exact three candidate artifacts exist.
"""


WORKSPACE_AGENTS = """# Isolated controlled-synthetic V3 constructor workspace

Follow the rendered constructor prompt. Read only `inputs/`, `repository/`, and
`tools/run_public.py`. Write candidate output only under `candidate/`, with
optional temporary work under `.scratch/`. The nested `repository/AGENTS.md`
describes its target service path, but the repository itself is a read-only
frozen input: candidate artifacts belong under `candidate/`.

Do not inspect parent directories, Git metadata, other families, prior attempts,
researcher tests, sealed checks, references, validators, acquisition decisions,
evaluated-agent outcomes, human judgments, or risk labels. Do not use network
access. The external launcher runs the frozen machine validator after you stop.
"""


PUBLIC_CHECK_TOOL = r'''#!/usr/bin/env python3
"""Thin runner for the two frozen public callables; it adds no assertions."""
from __future__ import annotations
import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "repository"
sys.path.insert(0, str(REPOSITORY))

FAMILY = __FAMILY__
ENTRYPOINTS = __ENTRYPOINTS__

def load_python(path):
    spec = importlib.util.spec_from_file_location("constructor_candidate_service", path)
    if spec is None or spec.loader is None:
        raise ImportError("candidate service loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, "run")
    if not callable(function):
        raise TypeError("candidate must export callable run")
    return function

def load_x02(path):
    from fixture_api.x02_inputs import InvalidInput, cells, validate_request
    from fixture_api.x02_lowering import lower
    from fixture_api.x02_machine import Execution, run
    compiled = lower(path.read_text(encoding="utf-8"))
    def application(pattern, records, flags="NONE"):
        try:
            validate_request(pattern, records, flags)
        except InvalidInput:
            return Execution("INVALID_INPUT")
        return run(compiled, cells(pattern, records, flags), tuple(records))
    return application

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    args = parser.parse_args()
    service = (ROOT / args.service).resolve()
    if ROOT not in service.parents:
        raise ValueError("service must be inside workspace")
    application = load_x02(service) if FAMILY == "X02" else load_python(service)
    tests = importlib.import_module("public_tests")
    completed = []
    for name in ENTRYPOINTS:
        getattr(tests, name)(application)
        completed.append(name)
    print(json.dumps({"family_id": FAMILY, "public_entrypoints": completed, "status": "PASS"}, sort_keys=True))

if __name__ == "__main__":
    main()
'''


CHROOT_SCRIPT = r'''
root=$1
workspace=$2
codex=$3
code_mode_host=$4
shift 4
mount --make-rprivate /
mount --bind /usr "$root/usr"
mount -o remount,bind,ro "$root/usr"
mount --bind /opt/miniconda3 "$root/opt/miniconda3"
mount -o remount,bind,ro "$root/opt/miniconda3"
mount --bind "$codex" "$root/codex/codex"
mount -o remount,bind,ro "$root/codex/codex"
mount --bind "$code_mode_host" "$root/codex/codex-code-mode-host"
mount -o remount,bind,ro "$root/codex/codex-code-mode-host"
mount --bind "$workspace" "$root/workspace"
for member in AGENTS.md inputs repository tools; do
  mount --bind "$workspace/$member" "$root/workspace/$member"
  mount -o remount,bind,ro "$root/workspace/$member"
done
for directory in ssl alternatives; do
  if [ -d "/etc/$directory" ]; then
    mount --bind "/etc/$directory" "$root/etc/$directory"
    mount -o remount,bind,ro "$root/etc/$directory"
  fi
done
for name in resolv.conf hosts nsswitch.conf passwd group; do
  if [ -f "/etc/$name" ]; then
    mount --bind "/etc/$name" "$root/etc/$name"
    mount -o remount,bind,ro "$root/etc/$name"
  fi
done
for name in null random urandom; do
  mount --bind "/dev/$name" "$root/dev/$name"
done
mount -t tmpfs -o size=256m,nosuid,nodev tmpfs "$root/tmp"
mount -t proc -o nosuid,nodev,noexec proc "$root/proc"
exec /usr/sbin/chroot "$root" /usr/bin/env -i \
  HOME=/home/constructor CODEX_HOME=/codex-home \
  PATH=/opt/miniconda3/bin:/usr/bin:/bin \
  LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
  SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
  /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
  --no-new-privs /codex/codex "$@"
'''


TOOL_ITEM_TYPES = {
    "command_execution", "file_change", "mcp_tool_call", "web_search",
    "image_generation", "dynamic_tool_call", "tool_call", "function_call",
}


class InfrastructureBlocker(RuntimeError):
    """A systemic condition that prevents further exact construction."""


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
    write_new(path, json.dumps(value, indent=2, sort_keys=True, default=repr).encode("utf-8") + b"\n")


def replace_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=repr) + "\n", encoding="utf-8")
    os.replace(temporary, path)


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


def historical_tree_sha256(root: Path) -> str:
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
    return sha256_bytes(canonical(rows))


def runtime_freeze_commit() -> str:
    receipt = read_json(REPO_ROOT / RUNTIME_RECEIPT_PATH)
    value = receipt.get("freeze_commit")
    if not isinstance(value, str) or len(value) != 40:
        raise ValueError("V2 runtime freeze receipt lacks an exact commit")
    return value


def verify_runtime_release() -> dict[str, Any]:
    receipt = read_json(REPO_ROOT / RUNTIME_RECEIPT_PATH)
    manifest_path = REPO_ROOT / RUNTIME_MANIFEST_PATH
    manifest = read_json(manifest_path)
    if receipt.get("status") != "COMMITTED_PRE_X_FAMILY_CONSTRUCTION":
        raise ValueError("V2 runtime freeze receipt is not pre-construction committed")
    if receipt.get("runtime_manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("V2 runtime manifest differs from its commit receipt")
    if manifest.get("release_id") != RUNTIME_RELEASE_ID:
        raise ValueError("wrong V2 runtime amendment identity")
    if manifest.get("x_family_constructor_attempts") != 0:
        raise ValueError("V2 runtime amendment was not frozen before X-family construction")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        raise ValueError("V2 runtime manifest inventory is missing")
    for relative, expected in inventory.items():
        path = REPO_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"V2 frozen runtime file is missing: {relative}")
        observed = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        if observed != expected:
            raise ValueError(f"V2 frozen runtime file changed: {relative}")
    if sha256_bytes(canonical(inventory)) != manifest.get("inventory_sha256"):
        raise ValueError("V2 runtime inventory digest differs")
    runtime = read_json(REPO_ROOT / RUNTIME_CONFIGURATION_PATH)
    constructor = runtime.get("constructor", {})
    expected_constructor = {
        "model_identifier": CLI_MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "fast_mode_enabled": FAST_MODE_ENABLED,
        "service_tier": SERVICE_TIER,
        "codex_cli_version": CODEX_CLI_VERSION,
        "codex_executable_sha256": CODEX_SHA256,
        "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
    }
    for key, value in expected_constructor.items():
        if constructor.get(key) != value:
            raise ValueError(f"V2 frozen constructor configuration changed: {key}")
    if sha256_file(CODEX) != CODEX_SHA256:
        raise ValueError("frozen Codex executable is unavailable or changed")
    if sha256_file(CODE_MODE_HOST) != CODE_MODE_HOST_SHA256:
        raise ValueError("frozen Codex code-mode host is unavailable or changed")
    if historical_tree_sha256(REPO_ROOT / V1_ROOT) != V1_TREE_SHA256:
        raise ValueError("controlled_v3_construction_v1 changed")
    freeze_commit = runtime_freeze_commit()
    ancestor = capture(["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"])
    if ancestor["returncode"] != 0:
        raise ValueError("HEAD does not contain the committed V2 runtime freeze")
    frozen_blob = subprocess.run(
        ["git", "show", f"{freeze_commit}:{RUNTIME_MANIFEST_PATH.as_posix()}"],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if frozen_blob.returncode != 0 or frozen_blob.stdout != manifest_path.read_bytes():
        raise ValueError("committed V2 runtime manifest differs from the working copy")
    return {"manifest": manifest, "receipt": receipt, "constructor": constructor}


def assert_clean_frozen_tree() -> None:
    head = capture(["git", "rev-parse", "HEAD"])
    if head["returncode"]:
        raise ValueError("unable to identify construction HEAD")
    base = capture(["git", "merge-base", "--is-ancestor", FREEZE_COMMIT, head["stdout"].strip()])
    if base["returncode"] != 0:
        raise ValueError("construction HEAD does not descend from the scientific freeze")
    unstaged = capture(["git", "diff", "--name-only", "--", "."])
    staged = capture(["git", "diff", "--cached", "--name-only", "--", "."])
    if unstaged["returncode"] or staged["returncode"]:
        raise ValueError("unable to inspect tracked worktree state")
    if unstaged["stdout"].strip() or staged["stdout"].strip():
        raise ValueError("tracked files differ from the frozen commit")


def load_bindings() -> dict[str, dict[str, Any]]:
    value = read_json(REPO_ROOT / BINDINGS_PATH)
    if tuple(value) != IN_SCOPE:
        raise ValueError("constructor binding order/scope differs from frozen order")
    if any(row.get("attempt_cap") != 4 for row in value.values()):
        raise ValueError("constructor attempt cap differs from four")
    return value


def verify_risk_labels() -> None:
    value = read_json(REPO_ROOT / RISK_PATH)
    observed: dict[str, list[str]] = {name: [] for name in RISK_LABELS}
    for family, row in value.get("families", {}).items():
        label = row.get("new")
        if label in observed:
            observed[label].append(family)
    for label, expected in RISK_LABELS.items():
        if tuple(observed[label]) != expected:
            raise ValueError(f"prospective ceiling-risk metadata changed for {label}")
    if value.get("advisory_only") is not True or value.get("affects_admission") is not False:
        raise ValueError("ceiling-risk metadata is not advisory-only")


def verify_constructor_release() -> dict[str, Any]:
    value = read_json(REPO_ROOT / CONSTRUCTOR_RELEASE_PATH)
    expected = {
        "model": FROZEN_MODEL,
        "version": FROZEN_VERSION,
        "timeout_seconds": TIMEOUT_SECONDS,
        "tool_call_limit": TOOL_CALL_LIMIT,
        "maximum_output_tokens": MAXIMUM_OUTPUT_TOKENS,
    }
    if value.get("constructor") != expected:
        raise ValueError("frozen constructor configuration changed")
    return value


def verify_frozen(*, preflight_isolation: bool = False) -> dict[str, Any]:
    assert_clean_frozen_tree()
    runtime = verify_runtime_release()
    manifest = envelope.verify(REPO_ROOT, expected_manifest_sha256=EXPECTED_MANIFEST_SHA256)
    if manifest.get("release_id") != RELEASE_ID:
        raise ValueError("wrong difficulty-amendment identity")
    bindings = load_bindings()
    if tuple(control.IN_SCOPE) != IN_SCOPE or tuple(control.EXCLUDED) != EXCLUDED:
        raise ValueError("frozen machine-control scope differs")
    if control.CONSTRUCTOR_ATTEMPT_LIMIT != 4 or control.CONSTRUCTOR_DEADLINE_SECONDS != TIMEOUT_SECONDS:
        raise ValueError("frozen machine-control constructor limits differ")
    verify_risk_labels()
    verify_constructor_release()
    if sha256_file(REPO_ROOT / MANIFEST_PATH) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("difficulty manifest differs from external hash")
    if preflight_isolation:
        isolated_preflight()
    return {"manifest": manifest, "bindings": bindings, "runtime": runtime}


def attempt_name(number: int) -> str:
    if number not in (1, 2, 3, 4):
        raise ValueError("attempt number must be 1 through 4")
    return f"attempt-{number:03d}"


def attempt_root(family: str, number: int) -> Path:
    return REPO_ROOT / RAW_ROOT / family / attempt_name(number)


def construction_nonce(family: str, number: int) -> str:
    return sha256_bytes(f"{EXPECTED_MANIFEST_SHA256}:{family}:{attempt_name(number)}".encode("ascii"))


def render_prompt(family: str, number: int, binding: dict[str, Any]) -> bytes:
    run_binding = {
        "schema_version": "controlled-synthetic-v3-constructor-run-binding/1",
        "release_id": RELEASE_ID,
        "freeze_commit": FREEZE_COMMIT,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "family_id": family,
        "frozen_order": IN_SCOPE.index(family) + 1,
        "attempt": attempt_name(number),
        "attempt_cap": 4,
        "construction_nonce": construction_nonce(family, number),
        "construction_nonce_is_not_sampling_seed": True,
        "sampling_seed": None,
        "prior_attempt_feedback": False,
        "service_path": binding["service_path"],
        "candidate_artifacts": [
            f"B/{binding['service_path']}", "feature.patch", "security.patch"
        ],
        "public_check_command": "python tools/run_public.py --service PATH",
        "allowed_read_roots": ["inputs", "repository", "tools/run_public.py", "AGENTS.md"],
        "allowed_write_roots": ["candidate", ".scratch"],
        "ceiling_risk_label_exposed": False,
    }
    return (
        PROMPT_TEMPLATE.rstrip()
        + "\n\n## Frozen run binding\n\n```json\n"
        + json.dumps(run_binding, indent=2, sort_keys=True)
        + "\n```\n"
    ).encode("utf-8")


def public_tool(family: str, binding: dict[str, Any]) -> bytes:
    entries = [item.split(":", 1)[1] for item in binding["public_check_entrypoints"]]
    text = PUBLIC_CHECK_TOOL.replace("__FAMILY__", repr(family)).replace("__ENTRYPOINTS__", repr(entries))
    return text.encode("utf-8")


def copy_new(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"bound input is missing or not regular: {source}")
    write_new(destination, source.read_bytes())


def copy_tree_new(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copytree(source, destination, symlinks=True)


def make_read_only(root: Path) -> None:
    for path in sorted([root, *root.rglob("*")], reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        if path.is_dir():
            path.chmod((mode & ~0o222) | 0o555)
        else:
            path.chmod(mode & ~0o222 & ~0o111)


def tree_snapshot(root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                entries.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
            elif stat.S_ISREG(metadata.st_mode):
                entries.append({
                    "path": relative,
                    "type": "file",
                    "bytes": metadata.st_size,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "sha256": sha256_file(path),
                })
            elif stat.S_ISDIR(metadata.st_mode):
                entries.append({"path": relative, "type": "directory", "mode": stat.S_IMODE(metadata.st_mode)})
            else:
                entries.append({"path": relative, "type": "special", "mode": stat.S_IMODE(metadata.st_mode)})
    return {
        "exists": root.exists(),
        "entries": entries,
        "tree_sha256": sha256_bytes(canonical(entries)),
    }


def initialize_chroot(root: Path) -> None:
    for directory in (
        "usr", "opt/miniconda3", "codex", "workspace", "etc/ssl", "etc/alternatives",
        "dev", "tmp", "proc", "home/constructor", "codex-home",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"), ("lib", "usr/lib"), ("lib64", "usr/lib64")):
        link = root / name
        if not link.exists():
            link.symlink_to(target)
    for name in ("resolv.conf", "hosts", "nsswitch.conf", "passwd", "group"):
        (root / "etc" / name).touch()
    for name in ("null", "random", "urandom"):
        (root / "dev" / name).touch()
    (root / "codex" / "codex").touch()
    (root / "codex" / "codex-code-mode-host").touch()
    codex_home = Path("/home/s224049759/.codex")
    for name in ("auth.json", "installation_id", "models_cache.json"):
        source = codex_home / name
        if source.is_file():
            shutil.copy2(source, root / "codex-home" / name)


def inside_codex_command(final_message: str) -> list[str]:
    return [
        "--ask-for-approval", "never",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--ephemeral",
        "--model", CLI_MODEL,
        "--config", f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--config", f'service_tier="{SERVICE_TIER}"',
        "--sandbox", "workspace-write",
        "--cd", "/workspace",
        "--skip-git-repo-check",
        "--json",
        "--color", "never",
        "--output-last-message", final_message,
        "-",
    ]


def isolated_command(root: Path, workspace: Path, inside: list[str]) -> list[str]:
    return [
        "/usr/bin/unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork",
        "/bin/sh", "-eu", "-c", CHROOT_SCRIPT, "sh",
        str(root), str(workspace), str(CODEX.resolve()), str(CODE_MODE_HOST.resolve()), *inside,
    ]


def isolated_preflight() -> None:
    if sha256_file(CODEX) != CODEX_SHA256 or sha256_file(CODE_MODE_HOST) != CODE_MODE_HOST_SHA256:
        raise ValueError("frozen Codex runtime binaries changed")
    host_result = capture([str(CODE_MODE_HOST), "--help"], timeout=120)
    if host_result["returncode"] != 0 or "Usage: codex-code-mode-host" not in host_result["stdout"]:
        raise ValueError("Codex code-mode host preflight failed")
    with tempfile.TemporaryDirectory(prefix="v3-constructor-preflight-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "root"
        workspace = temporary_root / "workspace"
        workspace.mkdir()
        for name in ("inputs", "repository", "tools", "candidate", ".scratch"):
            (workspace / name).mkdir()
        (workspace / "AGENTS.md").write_text(WORKSPACE_AGENTS, encoding="utf-8")
        initialize_chroot(root)
        result = capture(isolated_command(root, workspace, ["--version"]), timeout=120)
        if result["returncode"] != 0 or "codex-cli" not in result["stdout"]:
            raise ValueError("isolated Codex preflight failed: " + result["stderr"][:500])


def control_freeze_value() -> dict[str, Any]:
    return {
        "schema_version": "controlled-synthetic-v3-launcher-control-freeze/1",
        "release_id": RELEASE_ID,
        "freeze_commit": FREEZE_COMMIT,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "construction_version": "controlled_v3_construction_v2",
        "runtime_release_id": RUNTIME_RELEASE_ID,
        "runtime_freeze_commit": runtime_freeze_commit(),
        "runtime_manifest_sha256": sha256_file(REPO_ROOT / RUNTIME_MANIFEST_PATH),
        "bindings_sha256": sha256_file(REPO_ROOT / BINDINGS_PATH),
        "constructor_release_sha256": sha256_file(REPO_ROOT / CONSTRUCTOR_RELEASE_PATH),
        "risk_metadata_sha256": sha256_file(REPO_ROOT / RISK_PATH),
        "production_ledger_initial_sha256": sha256_file(REPO_ROOT / PRODUCTION_LEDGER_PATH),
        "launcher_sha256": sha256_file(Path(__file__).resolve()),
        "prompt_template_sha256": sha256_bytes(PROMPT_TEMPLATE.encode("utf-8")),
        "workspace_agents_sha256": sha256_bytes(WORKSPACE_AGENTS.encode("utf-8")),
        "public_check_template_sha256": sha256_bytes(PUBLIC_CHECK_TOOL.encode("utf-8")),
        "chroot_script_sha256": sha256_bytes(CHROOT_SCRIPT.encode("utf-8")),
        "constructor": {
            "frozen_model": FROZEN_MODEL,
            "frozen_version": FROZEN_VERSION,
            "resolved_official_model_id": CLI_MODEL,
            "reasoning_effort_override": REASONING_EFFORT,
            "fast_mode_enabled": FAST_MODE_ENABLED,
            "service_tier": SERVICE_TIER,
            "codex_cli_version": CODEX_CLI_VERSION,
            "codex_executable_sha256": CODEX_SHA256,
            "code_mode_host_path": str(CODE_MODE_HOST),
            "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
            "timeout_seconds": TIMEOUT_SECONDS,
            "tool_call_limit": TOOL_CALL_LIMIT,
            "maximum_output_tokens": MAXIMUM_OUTPUT_TOKENS,
        },
        "family_order": list(IN_SCOPE),
        "excluded_zero_attempts": list(EXCLUDED),
        "risk_labels_metadata_only": {key: list(value) for key, value in RISK_LABELS.items()},
        "evaluated_agents_enabled": False,
        "human_review_enabled": False,
    }


def initialize_control() -> None:
    expected = control_freeze_value()
    path = REPO_ROOT / CONTROL_FREEZE_PATH
    if path.is_file():
        observed = read_json(path)
        comparable = dict(observed)
        comparable.pop("frozen_at_utc", None)
        if comparable != expected:
            raise ValueError("post-freeze launcher controls changed after construction began")
    else:
        write_new_json(path, {**expected, "frozen_at_utc": utc_now()})
    ledger_path = REPO_ROOT / WORKING_LEDGER_PATH
    if not ledger_path.exists():
        value = control.pristine_ledger()
        if tuple(value["construction_order"]) != IN_SCOPE:
            raise ValueError("frozen ledger construction order differs")
        value["mutation_enabled"] = True
        value["release_commit"] = FREEZE_COMMIT
        value["release_manifest_sha256"] = EXPECTED_MANIFEST_SHA256
        write_new_json(ledger_path, value)


def materialize_attempt(family: str, number: int, binding: dict[str, Any]) -> dict[str, Any]:
    root = attempt_root(family, number)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {root}")
    workspace = root / "workspace"
    record = root / "record"
    workspace.mkdir(parents=True)
    record.mkdir()
    (workspace / "candidate").mkdir()
    (workspace / ".scratch").mkdir()
    write_new(workspace / "AGENTS.md", WORKSPACE_AGENTS.encode("utf-8"))
    task_source = REPO_ROOT / binding["scientific_task"]
    source_source = REPO_ROOT / binding["source"]
    repository_source = REPO_ROOT / binding["public_repository"]
    copy_new(task_source, workspace / "inputs/task.json")
    copy_new(source_source, workspace / "inputs/source" / source_source.name)
    copy_tree_new(repository_source, workspace / "repository")
    write_new(workspace / "tools/run_public.py", public_tool(family, binding))
    make_read_only(workspace / "inputs")
    make_read_only(workspace / "repository")
    make_read_only(workspace / "tools")
    (workspace / "AGENTS.md").chmod(0o444)
    prompt = render_prompt(family, number, binding)
    write_new(record / "prompt.txt", prompt)
    input_snapshot = tree_snapshot(workspace)
    manifest = {
        "schema_version": "controlled-synthetic-v3-render-record/1",
        "release_id": RELEASE_ID,
        "freeze_commit": FREEZE_COMMIT,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "family_id": family,
        "attempt": attempt_name(number),
        "rendered_at_utc": utc_now(),
        "construction_nonce": construction_nonce(family, number),
        "sampling_seed": None,
        "prior_attempt_feedback_present": False,
        "sealed_tests_present": False,
        "reference_states_present": False,
        "validator_present": False,
        "other_family_inputs_present": False,
        "evaluated_outcomes_present": False,
        "human_judgments_present": False,
        "ceiling_risk_label_present": False,
        "prompt_sha256": sha256_bytes(prompt),
        "bound_task_sha256": sha256_file(task_source),
        "bound_source_sha256": sha256_file(source_source),
        "bound_public_repository_snapshot": tree_snapshot(repository_source),
        "initial_workspace": input_snapshot,
    }
    write_new_json(record / "render_manifest.json", manifest)
    return manifest


def terminal_event_present(path: Path) -> bool:
    return telemetry(path)["terminal_event_present"]


def telemetry(path: Path) -> dict[str, Any]:
    terminal_types: list[str] = []
    tool_keys: set[str] = set()
    output_tokens: list[int] = []
    parse_errors = 0
    event_count = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(event, dict):
                continue
            event_count += 1
            event_type = event.get("type")
            if event_type in {"turn.completed", "turn.failed"}:
                terminal_types.append(str(event_type))
            if event_type == "turn.completed":
                usage = event.get("usage")
                if isinstance(usage, dict) and type(usage.get("output_tokens")) is int:
                    output_tokens.append(usage["output_tokens"])
            if event_type in {"item.started", "item.completed"}:
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") in TOOL_ITEM_TYPES:
                    identifier = item.get("id")
                    if isinstance(identifier, str):
                        tool_keys.add("id:" + identifier)
                    else:
                        tool_keys.add("item:" + sha256_bytes(canonical(item)))
    return {
        "event_count": event_count,
        "json_parse_errors": parse_errors,
        "terminal_event_present": bool(terminal_types),
        "terminal_event_types": terminal_types,
        "tool_calls": len(tool_keys),
        "output_tokens": max(output_tokens) if output_tokens else None,
        "all_reported_output_tokens": output_tokens,
    }


def terminate_group(process: subprocess.Popen[bytes], reason: str) -> tuple[int, str]:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=5), reason
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.wait(), reason + "_THEN_KILLED"


def execute_codex(
    command: list[str], *, workspace: Path, prompt: bytes, events: Path,
    stderr: Path, timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    terminal_seen_at: float | None = None
    timed_out = False
    tool_limit_exceeded = False
    termination_reason = "PROCESS_EXIT"
    with events.open("xb") as stdout_handle, stderr.open("xb") as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except BaseException:
            stderr_handle.write(traceback.format_exc().encode("utf-8", "replace"))
            return {
                "returncode": None,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": False,
                "tool_limit_exceeded": False,
                "termination_reason": "PROCESS_START_ERROR",
                "telemetry": telemetry(events),
            }
        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()
        while process.poll() is None:
            now = time.monotonic()
            observed = telemetry(events)
            if observed["tool_calls"] > TOOL_CALL_LIMIT:
                tool_limit_exceeded = True
                termination_reason = "TOOL_CALL_LIMIT_EXCEEDED"
                returncode, termination_reason = terminate_group(process, termination_reason)
                break
            if terminal_seen_at is None and observed["terminal_event_present"]:
                terminal_seen_at = now
            if terminal_seen_at is not None and now - terminal_seen_at >= POST_TERMINAL_GRACE_SECONDS:
                termination_reason = "TERMINATED_AFTER_RECORDED_TERMINAL_EVENT"
                returncode, termination_reason = terminate_group(process, termination_reason)
                break
            if now - started >= timeout_seconds:
                timed_out = True
                termination_reason = "TIMEOUT"
                returncode, termination_reason = terminate_group(process, termination_reason)
                break
            time.sleep(0.25)
        else:
            returncode = process.returncode
        if process.poll() is not None:
            returncode = process.returncode
    observed = telemetry(events)
    return {
        "returncode": returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "tool_limit_exceeded": tool_limit_exceeded,
        "termination_reason": termination_reason,
        "telemetry": observed,
    }


def validate_attempt(family: str, candidate: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = validator.validate_candidate(
            candidate,
            family,
            expected_release_sha256=EXPECTED_MANIFEST_SHA256,
        )
        return {
            "completed": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "result": result,
            "exception": None,
        }
    except BaseException as error:
        return {
            "completed": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "result": None,
            "exception": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }


def model_unavailable(record: Path) -> bool:
    text = ""
    for path in (record / "stderr.log", record / "events.jsonl"):
        if path.is_file():
            text += "\n" + path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    markers = (
        "model_not_found", "model not found", "unsupported model",
        "does not exist", "not supported when using codex",
        "not available for your account", "not available with this account",
    )
    return CLI_MODEL in lowered and any(marker in lowered for marker in markers)


def code_mode_unavailable(record: Path) -> bool:
    text = ""
    for path in (record / "stderr.log", record / "events.jsonl"):
        if path.is_file():
            text += "\n" + path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    return "code mode is unavailable" in lowered or "code mode will fail closed" in lowered


def classify(execution: dict[str, Any], validation: dict[str, Any], record: Path) -> tuple[list[str], bool]:
    categories: list[str] = []
    telemetry_value = execution["telemetry"]
    if model_unavailable(record):
        categories.append("CONSTRUCTOR_MODEL_UNAVAILABLE")
    if code_mode_unavailable(record):
        categories.append("CONSTRUCTOR_CODE_MODE_UNAVAILABLE")
    if execution["termination_reason"] == "PROCESS_START_ERROR":
        categories.append("CONSTRUCTOR_PROCESS_START_ERROR")
    if execution["timed_out"]:
        categories.append("CONSTRUCTOR_TIMEOUT")
    if execution["tool_limit_exceeded"] or telemetry_value["tool_calls"] > TOOL_CALL_LIMIT:
        categories.append("TOOL_CALL_LIMIT_EXCEEDED")
    output_tokens = telemetry_value["output_tokens"]
    if output_tokens is not None and output_tokens > MAXIMUM_OUTPUT_TOKENS:
        categories.append("OUTPUT_TOKEN_LIMIT_EXCEEDED")
    if execution["returncode"] not in (0, None) and not execution["timed_out"] and not execution["tool_limit_exceeded"]:
        categories.append("CONSTRUCTOR_PROCESS_ERROR")
    if not telemetry_value["terminal_event_present"]:
        categories.append("CONSTRUCTOR_TERMINAL_EVENT_MISSING")
    if not validation["completed"]:
        exception_type = (validation.get("exception") or {}).get("type")
        categories.append("CANDIDATE_INTEGRITY_ERROR" if exception_type == "IntegrityError" else "VALIDATOR_EXCEPTION")
    else:
        result = validation["result"]
        if not result.get("machine_valid"):
            rows = result.get("matrix", {}).values()
            if any(row.get("worker_status") != "COMPLETE" for row in rows if isinstance(row, dict)):
                categories.append("VALIDATOR_HARNESS_ERROR")
            else:
                categories.append("MACHINE_MATRIX_REJECT")
    execution_ok = (
        execution["returncode"] == 0
        and not execution["timed_out"]
        and not execution["tool_limit_exceeded"]
        and telemetry_value["terminal_event_present"]
        and (output_tokens is None or output_tokens <= MAXIMUM_OUTPUT_TOKENS)
        and not model_unavailable(record)
        and not code_mode_unavailable(record)
    )
    machine_admitted = execution_ok and validation["completed"] and validation["result"].get("machine_valid") is True
    if machine_admitted:
        categories = []
    elif not categories:
        categories = ["UNCLASSIFIED_MACHINE_REJECT"]
    return categories, machine_admitted


def candidate_hash(snapshot: dict[str, Any]) -> str:
    return sha256_bytes(canonical(snapshot.get("entries", [])))


def run_attempt(family: str, number: int) -> dict[str, Any]:
    verified = verify_frozen()
    initialize_control()
    bindings = verified["bindings"]
    binding = bindings[family]
    root = attempt_root(family, number)
    if root.exists():
        raise FileExistsError(f"attempt already exists: {root}")
    render = materialize_attempt(family, number, binding)
    workspace = root / "workspace"
    record = root / "record"
    prompt = (record / "prompt.txt").read_bytes()
    if sha256_bytes(prompt) != render["prompt_sha256"]:
        raise ValueError("rendered prompt hash mismatch")
    final_message_inside = "/workspace/.scratch/final_message.txt"
    inside = inside_codex_command(final_message_inside)
    controller = control.DisposableLedgerController(REPO_ROOT / WORKING_LEDGER_PATH)
    ledger_row = controller.begin(family, utc_now(), EXPECTED_MANIFEST_SHA256)
    if ledger_row["attempt"] != number:
        raise ValueError("disposable ledger attempt number differs")
    with tempfile.TemporaryDirectory(prefix=f"v3-{family.lower()}-{attempt_name(number)}-constructor-") as temporary:
        chroot_root = Path(temporary) / "root"
        initialize_chroot(chroot_root)
        command = isolated_command(chroot_root, workspace, inside)
        write_new_json(record / "started.json", {
            "schema_version": "controlled-synthetic-v3-attempt-start/1",
            "family_id": family,
            "attempt": attempt_name(number),
            "started_at_utc": ledger_row["started_at"],
            "ledger_row": ledger_row,
            "host_command": command,
            "inside_codex_command": ["codex", *inside],
            "codex_version": capture([str(CODEX), "--version"]),
            "frozen_constructor": verify_constructor_release()["constructor"],
            "resolved_model_id": CLI_MODEL,
            "reasoning_effort_override": REASONING_EFFORT,
            "fast_mode_enabled": FAST_MODE_ENABLED,
            "service_tier": SERVICE_TIER,
            "runtime_release_id": RUNTIME_RELEASE_ID,
            "runtime_freeze_commit": runtime_freeze_commit(),
            "runtime_manifest_sha256": sha256_file(REPO_ROOT / RUNTIME_MANIFEST_PATH),
            "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
            "python": sys.version,
            "platform": platform.platform(),
            "isolation": "user+mount+pid namespace; chroot; private proc/tmp; frozen inputs bind-read-only; no private study tree mounted",
            "temporary_constructor_root_retained": False,
        })
        execution = execute_codex(
            command,
            workspace=workspace,
            prompt=prompt,
            events=record / "events.jsonl",
            stderr=record / "stderr.log",
            timeout_seconds=TIMEOUT_SECONDS,
        )
    final_source = workspace / ".scratch/final_message.txt"
    if final_source.is_file():
        write_new(record / "final_message.txt", final_source.read_bytes())
    else:
        write_new(record / "final_message.txt", b"")
    validation_value = validate_attempt(family, workspace / "candidate")
    write_new_json(record / "validation.json", validation_value)
    workspace_final = tree_snapshot(workspace)
    candidate_snapshot = tree_snapshot(workspace / "candidate")
    write_new_json(record / "workspace_final_snapshot.json", workspace_final)
    write_new_json(record / "candidate_snapshot.json", candidate_snapshot)
    categories, admitted = classify(execution, validation_value, record)
    digest = candidate_hash(candidate_snapshot)
    machine_result = "MACHINE_VALID" if admitted else (
        "INFRASTRUCTURE_ERROR"
        if any(category in {
            "CONSTRUCTOR_MODEL_UNAVAILABLE", "CONSTRUCTOR_CODE_MODE_UNAVAILABLE",
            "CONSTRUCTOR_PROCESS_START_ERROR",
            "CONSTRUCTOR_TIMEOUT", "TOOL_CALL_LIMIT_EXCEEDED",
            "OUTPUT_TOKEN_LIMIT_EXCEEDED", "CONSTRUCTOR_PROCESS_ERROR",
            "CONSTRUCTOR_TERMINAL_EVENT_MISSING", "VALIDATOR_EXCEPTION",
            "VALIDATOR_HARNESS_ERROR",
        } for category in categories)
        else "MACHINE_INVALID"
    )
    completed_ledger_row = controller.finish(family, number, machine_result, digest)
    outcome = {
        "schema_version": "controlled-synthetic-v3-attempt-outcome/1",
        "release_id": RELEASE_ID,
        "freeze_commit": FREEZE_COMMIT,
        "construction_version": "controlled_v3_construction_v2",
        "runtime_release_id": RUNTIME_RELEASE_ID,
        "runtime_freeze_commit": runtime_freeze_commit(),
        "runtime_manifest_sha256": sha256_file(REPO_ROOT / RUNTIME_MANIFEST_PATH),
        "family_id": family,
        "attempt": attempt_name(number),
        "completed_at_utc": utc_now(),
        "execution": execution,
        "validation_sha256": sha256_file(record / "validation.json"),
        "candidate_sha256": digest,
        "candidate_snapshot_sha256": sha256_file(record / "candidate_snapshot.json"),
        "failure_categories": categories,
        "machine_result": machine_result,
        "machine_admitted": admitted,
        "first_admissible_retention": "retain immediately; never compare with or generate a later candidate",
        "ledger_row": completed_ledger_row,
        "manual_repair_performed": False,
        "evaluated_agents_run": 0,
        "human_reviews_performed": 0,
    }
    if admitted:
        result = validation_value["result"]
        outcome["accepted_hashes"] = {
            "candidate_sha256": digest,
            "state_tree_sha256": result["integrity"]["state_tree_sha256"],
            "feature_patch_sha256": result["integrity"]["feature_patch"]["sha256"],
            "security_patch_sha256": result["integrity"]["security_patch"]["sha256"],
        }
    else:
        outcome["accepted_hashes"] = None
    write_new_json(record / "outcome.json", outcome)
    write_new_json(record / "ledger_after_attempt.json", read_json(REPO_ROOT / WORKING_LEDGER_PATH))
    update_progress()
    if "CONSTRUCTOR_MODEL_UNAVAILABLE" in categories:
        raise InfrastructureBlocker(
            f"exact frozen constructor model {CLI_MODEL} is unavailable; see {record}"
        )
    if "CONSTRUCTOR_CODE_MODE_UNAVAILABLE" in categories:
        raise InfrastructureBlocker(
            f"frozen constructor code-mode host is unavailable; see {record}"
        )
    return outcome


def existing_outcomes(family: str) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for number in (1, 2, 3, 4):
        root = attempt_root(family, number)
        path = root / "record/outcome.json"
        if path.is_file():
            outcomes.append(read_json(path))
        elif root.exists():
            raise RuntimeError(f"incomplete append-only attempt requires audit: {root}")
        else:
            break
    return outcomes


def next_attempt_number(family: str) -> int | None:
    outcomes = existing_outcomes(family)
    if any(item.get("machine_admitted") is True for item in outcomes):
        return None
    if len(outcomes) >= 4:
        return None
    return len(outcomes) + 1


def run_family(family: str) -> dict[str, Any]:
    if family not in IN_SCOPE:
        raise ValueError(f"family is not in construction scope: {family}")
    while True:
        number = next_attempt_number(family)
        if number is None:
            break
        outcome = run_attempt(family, number)
        if outcome["machine_admitted"]:
            break
    return family_status(family)


def family_status(family: str) -> dict[str, Any]:
    outcomes = existing_outcomes(family)
    accepted = next((item for item in outcomes if item.get("machine_admitted") is True), None)
    state = "MACHINE_ADMITTED" if accepted else "CONSTRUCTION_EXHAUSTED" if len(outcomes) == 4 else "PENDING"
    return {
        "family_id": family,
        "ceiling_risk": next(label for label, members in RISK_LABELS.items() if family in members),
        "attempt_count": len(outcomes),
        "status": state,
        "accepted_attempt": accepted.get("attempt") if accepted else None,
        "accepted_candidate_hashes": accepted.get("accepted_hashes") if accepted else None,
        "attempts": [
            {
                "attempt": row.get("attempt"),
                "machine_result": row.get("machine_result"),
                "machine_admitted": row.get("machine_admitted"),
                "candidate_sha256": row.get("candidate_sha256"),
                "failure_categories": row.get("failure_categories", []),
            }
            for row in outcomes
        ],
    }


def report() -> dict[str, Any]:
    families = [family_status(family) for family in IN_SCOPE]
    excluded = [
        {
            "family_id": family,
            "attempt_count": 0,
            "status": "PRE_CONSTRUCTION_EXCLUDED_ZERO_ATTEMPTS",
        }
        for family in EXCLUDED
    ]
    categories = Counter(
        category
        for family in families
        for attempt in family["attempts"]
        for category in attempt["failure_categories"]
    )
    ledger = read_json(REPO_ROOT / WORKING_LEDGER_PATH) if (REPO_ROOT / WORKING_LEDGER_PATH).is_file() else None
    production_hash = sha256_file(REPO_ROOT / PRODUCTION_LEDGER_PATH)
    initial_production_hash = (
        read_json(REPO_ROOT / CONTROL_FREEZE_PATH).get("production_ledger_initial_sha256")
        if (REPO_ROOT / CONTROL_FREEZE_PATH).is_file() else None
    )
    return {
        "schema_version": "controlled-synthetic-v3-construction-report/1",
        "release_id": RELEASE_ID,
        "freeze_commit": FREEZE_COMMIT,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "construction_version": "controlled_v3_construction_v2",
        "runtime_release_id": RUNTIME_RELEASE_ID,
        "runtime_freeze_commit": runtime_freeze_commit(),
        "runtime_manifest_sha256": sha256_file(REPO_ROOT / RUNTIME_MANIFEST_PATH),
        "family_order": list(IN_SCOPE),
        "families": families,
        "excluded": excluded,
        "resolved_count": sum(row["status"] != "PENDING" for row in families),
        "machine_admitted_count": sum(row["status"] == "MACHINE_ADMITTED" for row in families),
        "construction_exhausted_count": sum(row["status"] == "CONSTRUCTION_EXHAUSTED" for row in families),
        "pending_count": sum(row["status"] == "PENDING" for row in families),
        "total_constructor_attempts": sum(row["attempt_count"] for row in families),
        "constructor_failure_categories": dict(sorted(categories.items())),
        "accepted_candidate_hashes": {
            row["family_id"]: row["accepted_candidate_hashes"]
            for row in families if row["accepted_candidate_hashes"] is not None
        },
        "frozen_artifacts_unchanged": (
            production_hash == initial_production_hash
            and capture(["git", "diff", "--quiet", "HEAD", "--", "."])["returncode"] == 0
            and sha256_file(REPO_ROOT / MANIFEST_PATH) == EXPECTED_MANIFEST_SHA256
        ),
        "production_ledger_sha256": production_hash,
        "working_ledger": ledger,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }


def update_progress() -> dict[str, Any]:
    value = report()
    value["reported_at_utc"] = utc_now()
    replace_json(REPO_ROOT / PROGRESS_PATH, value)
    return value


def finalize_report() -> dict[str, Any]:
    verify_frozen()
    value = report()
    if value["pending_count"] != 0:
        raise ValueError("cannot finalize while construction families remain pending")
    value["completed_at_utc"] = utc_now()
    path = REPO_ROOT / FINAL_REPORT_PATH
    if path.exists():
        if read_json(path) != value:
            raise FileExistsError("refusing to overwrite differing final construction report")
    else:
        write_new_json(path, value)
    update_progress()
    return value


def run_all() -> dict[str, Any]:
    verify_frozen(preflight_isolation=True)
    initialize_control()
    results = []
    for family in IN_SCOPE:
        results.append(run_family(family))
    return finalize_report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=IN_SCOPE)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.family, args.all, args.status, args.verify))
    if selected != 1:
        parser.error("choose exactly one of --family, --all, --status, or --verify")
    try:
        if args.verify:
            result: object = verify_frozen(preflight_isolation=True)
            result = {
                "status": "VERIFIED",
                "release_id": RELEASE_ID,
                "freeze_commit": FREEZE_COMMIT,
                "manifest_sha256": EXPECTED_MANIFEST_SHA256,
                "construction_version": "controlled_v3_construction_v2",
                "runtime_release_id": RUNTIME_RELEASE_ID,
                "runtime_freeze_commit": runtime_freeze_commit(),
                "runtime_manifest_sha256": sha256_file(REPO_ROOT / RUNTIME_MANIFEST_PATH),
                "constructor": verify_constructor_release()["constructor"],
                "resolved_model_id": CLI_MODEL,
                "reasoning_effort_override": REASONING_EFFORT,
                "fast_mode_enabled": FAST_MODE_ENABLED,
                "service_tier": SERVICE_TIER,
                "codex_cli_version": CODEX_CLI_VERSION,
                "codex_executable_sha256": CODEX_SHA256,
                "code_mode_host_sha256": CODE_MODE_HOST_SHA256,
                "family_order": list(IN_SCOPE),
                "excluded_zero_attempts": list(EXCLUDED),
            }
        elif args.status:
            initialize_control()
            result = update_progress()
        elif args.family:
            verify_frozen(preflight_isolation=True)
            initialize_control()
            result = run_family(args.family)
        else:
            result = run_all()
        print(json.dumps(result, indent=2, sort_keys=True, default=repr))
        return 0
    except InfrastructureBlocker as error:
        value = update_progress()
        value["infrastructure_blocker"] = {
            "recorded_at_utc": utc_now(),
            "type": type(error).__name__,
            "message": str(error),
        }
        replace_json(REPO_ROOT / PROGRESS_PATH, value)
        print(json.dumps(value, indent=2, sort_keys=True, default=repr))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
