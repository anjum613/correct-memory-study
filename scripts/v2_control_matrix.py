#!/usr/bin/env python3
"""Run frozen functionality/security controls without model inference.

Axios, Aim, and HTTPX are reconstructed from V2-only content-addressed overlays.
Every evaluator runs against a disposable copy, so no V1 family or artifact is
mutated and no preserved historical dirty worktree is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from cmpilot.v2_snapshot_overlay import reconstruct_snapshot


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "artifacts/v2-preflight/control-matrix.json"
FAMILIES = (
    "mcp-pinot-v1",
    "onnx-v1",
    "axios-v1",
    "aim-v1",
    "httpx-v1",
    "djoser-v1",
)
OVERLAY_FAMILIES = frozenset(("axios-v1", "aim-v1", "httpx-v1"))
OVERLAY_MANIFEST = ROOT / "v2/fixtures/snapshot-overlays/manifest.json"
AXIOS_NODE = Path(
    "/home/s224049759/projects/correct-memory-study-worktrees/"
    "track-b-mcp-pinot-v01/tmp/axios-node-runtime-v1/bin/node"
)


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe(family_root: Path, kind: str, repository: Path) -> dict[str, Any]:
    evaluator = family_root / "oracles" / kind / "evaluate.py"
    environment = {
        "HOME": str(repository.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(repository.parent),
    }
    if family_root.name == "axios-v1":
        environment["CMPILOT_AXIOS_NODE"] = str(AXIOS_NODE)
    completed = subprocess.run(
        [
            "/opt/miniconda3/bin/python",
            "-B",
            str(evaluator),
            "--repository",
            str(repository),
            "--timeout-seconds",
            "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    payload: dict[str, Any] | None = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
            break
    return {
        "complete": bool(payload and payload.get("complete") is True),
        "passed": bool(payload and payload.get("passed") is True),
        "returncode": completed.returncode,
        "payload": payload,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stdout": completed.stdout[-2000:],
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
        "stderr": completed.stderr[-2000:],
    }


def _evaluate(family_root: Path, repository: Path) -> dict[str, Any]:
    return {
        "V1_FUNCTIONALITY": _probe(family_root, "functional", repository),
        "SECURITY": _probe(family_root, "security", repository),
        "TASK_COMPLETION": {
            "complete": False,
            "passed": False,
            "status": "BLOCKED_NON_IDENTIFIABLE",
            "reason": (
                "the frozen faithful-reuse reference is NO_CHANGE_BASELINE, so a "
                "treatment-blind final-state endpoint cannot distinguish it from untouched I"
            ),
        },
    }


def _apply_safe_patch(family_root: Path, repository: Path) -> dict[str, Any]:
    patch = family_root / "references/safe-control/secure.patch"
    initialized = subprocess.run(
        ["git", "init", "-q", str(repository)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if initialized.returncode != 0:
        return {
            "returncode": initialized.returncode,
            "patch_sha256": _sha256_file(patch),
            "stdout": initialized.stdout[-2000:],
            "stderr": initialized.stderr[-2000:],
        }
    completed = subprocess.run(
        ["git", "apply", str(patch)],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "returncode": completed.returncode,
        "patch_sha256": _sha256_file(patch),
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def run_family(family: str, scratch_root: Path) -> dict[str, Any]:
    family_root = ROOT / "families" / family
    if not family_root.is_dir():
        return {"family": family, "status": "BLOCKED", "reason": "family source unavailable"}
    reference = json.loads(
        (family_root / "references/faithful-reuse/reference.json").read_text()
    )
    application = reference.get("application")
    if isinstance(application, dict):
        application = application.get("application")
    family_scratch = scratch_root / family
    if family in OVERLAY_FAMILIES:
        source_repo = family_scratch / "reconstructed-invalidated"
        reconstruct_snapshot(
            repository_root=ROOT,
            manifest_path=OVERLAY_MANIFEST,
            family=family,
            state="invalidated",
            destination=source_repo,
        )
        source_kind = "v2_content_addressed_overlay"
    else:
        source_repo = family_root / "repositories/invalidated"
        source_kind = "v2_git_checkout"
    baseline = family_scratch / "baseline"
    shutil.copytree(source_repo, baseline, symlinks=True)

    baseline_result = _evaluate(family_root, baseline)
    irrelevant = family_scratch / "irrelevant"
    shutil.copytree(baseline, irrelevant, symlinks=True)
    irrelevant_file = irrelevant / ".v2-irrelevant-control.txt"
    irrelevant_file.write_text("nonempty patch unrelated to requested behavior\n")
    irrelevant_result = _evaluate(family_root, irrelevant)

    safe = family_scratch / "safe"
    shutil.copytree(baseline, safe, symlinks=True)
    application_result = _apply_safe_patch(family_root, safe)
    safe_result = (
        _evaluate(family_root, safe)
        if application_result["returncode"] == 0
        else {"status": "BLOCKED_SAFE_PATCH_APPLICATION"}
    )
    aliased = {
        state: {
            **baseline_result,
            "evidence_alias": "one executed baseline; byte-identical repository state",
        }
        for state in ("UNTOUCHED_I", "EMPTY_PATCH", "FAITHFUL_REUSE")
    }
    return {
        "family": family,
        "status": "PASS",
        "family_source": str(family_root),
        "family_source_kind": source_kind,
        "faithful_application": application,
        "states": {
            **aliased,
            "IRRELEVANT_PATCH": irrelevant_result,
            "SAFE_CONTROL": {**safe_result, "patch_application": application_result},
        },
    }


def build_matrix(output: Path, *, temporary_parent: Path | None = None) -> dict[str, Any]:
    temporary_parent = Path(tempfile.gettempdir()) if temporary_parent is None else temporary_parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="control-matrix-", dir=temporary_parent) as name:
        rows = [run_family(family, Path(name)) for family in FAMILIES]
    record = {
        "schema": "cmpilot-v2-control-matrix-v1",
        "model_inference": False,
        "families": rows,
    }
    payload = _canonical(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    record = build_matrix(args.output)
    print(json.dumps({"families": len(record["families"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
