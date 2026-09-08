#!/usr/bin/env python3
"""Public-only constructor check copied into isolated workspaces.

This helper intentionally has no catalog, hidden-test, validator, or reference
state dependency. It is not the admission decision.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path.cwd()
EXPECTED = {"B/app/service.py", "feature.patch", "security.patch"}


def files_under(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():
            relative = path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def apply_patch(repo: Path, patch: Path) -> tuple[bool, str]:
    process = subprocess.run(
        ["git", "apply", "--check", "--whitespace=error-all", str(patch)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode:
        return False, process.stdout
    process = subprocess.run(
        ["git", "apply", "--whitespace=error-all", str(patch)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return process.returncode == 0, process.stdout


def run_tests(repo: Path, tests: Path) -> tuple[bool, str]:
    outputs: list[str] = []
    success = True
    for test in sorted(tests.rglob("test_*.py")):
        command = (
            "import runpy,sys; "
            f"sys.path.insert(0, {str(repo)!r}); "
            f"runpy.run_path({str(test)!r}, run_name='__main__')"
        )
        process = subprocess.run(
            [sys.executable, "-I", "-c", command],
            cwd=repo,
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        outputs.append(process.stdout)
        success = success and process.returncode == 0
    return success, "\n".join(outputs)[-4000:]


def main() -> int:
    result: dict[str, object] = {"candidate_files": sorted(files_under(ROOT / "candidate"))}
    if set(result["candidate_files"]) != EXPECTED:
        result["error"] = f"candidate must contain exactly {sorted(EXPECTED)}"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    with tempfile.TemporaryDirectory(prefix="controlled-v2-public-") as temp:
        base = Path(temp)
        b_repo = base / "B"
        copy_tree(ROOT / "inputs/target/scaffold", b_repo)
        service = b_repo / "app/service.py"
        service.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "candidate/B/app/service.py", service)
        b_existing, _ = run_tests(b_repo, ROOT / "inputs/target/tests/public_existing")
        b_feature, _ = run_tests(b_repo, ROOT / "inputs/target/tests/public_feature")
        result["B_existing"] = b_existing
        result["B_requested_feature_fails"] = not b_feature

        u_repo = base / "U"
        shutil.copytree(b_repo, u_repo)
        applied, output = apply_patch(u_repo, ROOT / "candidate/feature.patch")
        result["feature_patch_applies"] = applied
        if not applied:
            result["feature_patch_output"] = output
        else:
            u_existing, _ = run_tests(u_repo, ROOT / "inputs/target/tests/public_existing")
            u_feature, _ = run_tests(u_repo, ROOT / "inputs/target/tests/public_feature")
            result["U_existing"] = u_existing
            result["U_requested_feature"] = u_feature

            r_repo = base / "R"
            shutil.copytree(u_repo, r_repo)
            applied, output = apply_patch(r_repo, ROOT / "candidate/security.patch")
            result["security_patch_applies"] = applied
            if not applied:
                result["security_patch_output"] = output
            else:
                r_existing, _ = run_tests(r_repo, ROOT / "inputs/target/tests/public_existing")
                r_feature, _ = run_tests(r_repo, ROOT / "inputs/target/tests/public_feature")
                result["R_existing"] = r_existing
                result["R_requested_feature"] = r_feature
    required = (
        "B_existing",
        "B_requested_feature_fails",
        "feature_patch_applies",
        "U_existing",
        "U_requested_feature",
        "security_patch_applies",
        "R_existing",
        "R_requested_feature",
    )
    passed = all(result.get(name) is True for name in required)
    result["public_check_passed"] = passed
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
