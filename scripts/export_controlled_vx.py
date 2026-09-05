#!/usr/bin/env python3
"""Corrected VX export, without changing frozen construction or raw patches.

The frozen export called git apply below an enclosing Git worktree. Extended
Git patches can be silently skipped there. Derive outside any Git repository,
check actual trees, then copy byte-identical artifacts into the worktree.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import controlled_vx as vx


def check_actual_trees(identifier, directory, test_root):
    case = vx.CASES[identifier]
    matrix = {}
    for state in ("B", "U", "R"):
        repo = directory / state
        if set(vx.inventory(repo)) != set(vx.repo_files(case)):
            raise ValueError("unexpected exported tree topology")
        for relative in vx.ALLOWED:
            vx.python_policy(repo / relative)
        for relative in set(vx.repo_files(case)) - vx.ALLOWED:
            if (repo / relative).read_text() != vx.repo_files(case)[relative]:
                raise ValueError("fixed runtime changed")
        matrix[state] = {
            kind: vx.run_tests(repo, case[key], test_root)
            for kind, key in (("existing", "existing_tests"),
                              ("feature", "feature_tests"),
                              ("invariant", "invariant_tests"))
        }
    passed = (
        matrix["B"]["existing"]["passed"]
        and not matrix["B"]["feature"]["passed"]
        and matrix["B"]["invariant"]["passed"]
        and all(matrix[state][kind]["passed"] for state in ("U", "R")
                for kind in ("existing", "feature"))
        and matrix["U"]["invariant"]["focal_assertion_failure"]
        and not matrix["U"]["invariant"]["timed_out"]
        and matrix["R"]["invariant"]["passed"]
    )
    if not passed:
        raise ValueError(f"actual exported trees fail the frozen matrix: {identifier}")
    return matrix


def derive_family(identifier, candidate, destination, test_root):
    if destination.exists():
        raise ValueError("refusing to overwrite a derivation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    discovery = subprocess.run(["git", "rev-parse", "--show-toplevel"],
        cwd=destination.parent, capture_output=True, text=True, timeout=10)
    if discovery.returncode == 0:
        raise ValueError("derivation must be outside every Git worktree")
    verified = vx.validate(identifier, candidate)
    if not verified["machine_valid"]:
        raise ValueError("recorded candidate failed replay")
    shutil.copytree(vx.BASE / "inputs" / identifier, destination)
    shutil.copytree(destination / "B", destination / "U")
    vx.apply_patch(destination / "U", (candidate / "feature.patch").read_text(), label="feature")
    shutil.copytree(destination / "U", destination / "R")
    vx.apply_patch(destination / "R", (candidate / "security.patch").read_text(), label="security")
    inventories = {state: vx.inventory(destination / state) for state in ("B", "U", "R")}
    if inventories["B"] == inventories["U"] or inventories["U"] == inventories["R"]:
        raise ValueError("a patch was a no-op during export")
    verified["matrix"] = check_actual_trees(identifier, destination, test_root)
    verified["actual_export_trees_verified"] = True
    verified["export_derivation"] = "outside-Git application plus actual-tree checks"
    vx.save_json(destination / "verification.json", verified)
    return verified


def export():
    vx.verify_release()
    if (vx.BASE / "accepted").exists() or (vx.BASE / "cohort_manifest.json").exists():
        raise ValueError("refusing to overwrite an export; retain any failed export separately")
    cohort = []
    with tempfile.TemporaryDirectory(prefix="vx-corrected-export-", dir="/tmp") as temporary:
        temporary = Path(temporary)
        staged = temporary / "accepted"
        for identifier in vx.CASES:
            records = []
            for path in sorted((vx.BASE / "acquisitions" / identifier).glob("attempt-*/record/outcome.json")):
                outcome = json.loads(path.read_text())
                if outcome["accepted"]:
                    records.append((path.parent.parent, outcome))
            if len(records) != 1:
                raise ValueError(f"{identifier}: expected exactly one first-valid candidate")
            attempt, outcome = records[0]
            candidate = attempt / "workspace/candidate"
            if vx.inventory(candidate) != outcome["candidate_sha256"]:
                raise ValueError("raw candidate changed after construction")
            destination = staged / identifier
            verified = derive_family(identifier, candidate, destination, temporary / "checks")
            cohort.append({"family": identifier, "attempt": attempt.name,
                "raw_attempt": attempt.relative_to(ROOT).as_posix(),
                "artifact_sha256": vx.inventory(destination), "complexity": verified["complexity"]})
        shutil.copytree(staged, vx.BASE / "accepted")
        if vx.inventory(staged) != vx.inventory(vx.BASE / "accepted"):
            raise ValueError("copied export differs from verified derivation")
    manifest = {"status": "SIX_DEVELOPMENT_STIMULI_MACHINE_VERIFIED",
        "created_at": vx.now(), "release_sha256": vx.digest((vx.BASE / "release.json").read_bytes()),
        "exporter_sha256": vx.digest(Path(__file__).read_bytes()),
        "export_schema": "VX_OUTSIDE_GIT_EXPORT_2", "families": cohort,
        "evaluated_agent_runs": 0, "effect_size": "UNMEASURED",
        "semantic_scope": "in-memory simulation contracts"}
    vx.save_json(vx.BASE / "cohort_manifest.json", manifest)
    return {"exported": len(cohort), "actual_trees_verified": True,
            "release_unchanged": bool(vx.verify_release())}


if __name__ == "__main__":
    print(json.dumps(export(), indent=2, sort_keys=True))
