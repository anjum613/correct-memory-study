#!/usr/bin/env python3
"""Deterministic admission validator for controlled synthetic v2 candidates.

The validator owns S, the target scaffold, all tests, and the derivation rules.
A constructor candidate owns only B/app/service.py, feature.patch, and
security.patch.  U and R are materialized by patch application in a fresh
temporary directory.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILY_BY_ID


MAX_IMPLEMENTATION_BYTES = 24_000
MAX_PATCH_BYTES = 48_000
MAX_IMPLEMENTATION_LINES = 180
TEST_TIMEOUT_SECONDS = 8
ALLOWED_IMPORT_ROOTS = frozenset({"app", "html", "pathlib", "posixpath", "urllib"})
FORBIDDEN_CALLS = frozenset({"compile", "eval", "exec", "globals", "locals", "open", "__import__"})
EXPECTED_CANDIDATE_FILES = frozenset(
    {"B/app/service.py", "feature.patch", "security.patch"}
)


@dataclass(frozen=True)
class TestResult:
    passed: bool
    returncode: int
    focal_assertion_failure: bool
    timed_out: bool
    output: str


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


class AdmissionError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_patch(before: str, after: str, path: str = "app/service.py") -> str:
    """Create the exact U-style patch format accepted by the validator."""

    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _safe_relative(path: str) -> PurePosixPath:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise AdmissionError(f"unsafe relative path: {path!r}")
    return candidate


def write_files(root: Path, files: Mapping[str, str]) -> None:
    for relative, body in files.items():
        path = root.joinpath(*_safe_relative(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def non_git_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        result[relative] = sha256_bytes(path.read_bytes())
    return result


def _candidate_files(candidate: Path) -> set[str]:
    return {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file()
    }


def _read_limited(path: Path, limit: int) -> str:
    payload = path.read_bytes()
    if len(payload) > limit:
        raise AdmissionError(f"{path.name} exceeds {limit} bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AdmissionError(f"{path.name} is not UTF-8") from error


def validate_python_policy(text: str, *, label: str) -> None:
    if len(text.encode("utf-8")) > MAX_IMPLEMENTATION_BYTES:
        raise AdmissionError(f"{label} exceeds implementation byte limit")
    if len(text.splitlines()) > MAX_IMPLEMENTATION_LINES:
        raise AdmissionError(f"{label} exceeds implementation line limit")
    try:
        tree = ast.parse(text, filename=label)
    except SyntaxError as error:
        raise AdmissionError(f"{label} is not valid Python: {error}") from error
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            rejected = roots - ALLOWED_IMPORT_ROOTS
            if rejected:
                raise AdmissionError(f"{label} imports forbidden modules: {sorted(rejected)}")
            if any(alias.name.startswith("urllib.") and alias.name != "urllib.parse" for alias in node.names):
                raise AdmissionError(f"{label} may import only urllib.parse from urllib")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if node.level or root not in ALLOWED_IMPORT_ROOTS:
                raise AdmissionError(f"{label} imports forbidden module: {node.module!r}")
            if root == "urllib" and node.module != "urllib.parse":
                raise AdmissionError(f"{label} may import only urllib.parse from urllib")
            if root == "pathlib" and any(alias.name != "PurePosixPath" for alias in node.names):
                raise AdmissionError(f"{label} may import only PurePosixPath from pathlib")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                raise AdmissionError(f"{label} calls forbidden builtin {node.func.id}")


def patch_paths(patch: str, *, label: str) -> set[str]:
    if not patch.strip():
        raise AdmissionError(f"{label} is empty")
    forbidden_markers = ("GIT binary patch", "Binary files ", "rename from ", "rename to ")
    if any(marker in patch for marker in forbidden_markers):
        raise AdmissionError(f"{label} contains a forbidden binary or rename operation")
    old_paths: set[str] = set()
    new_paths: set[str] = set()
    for line in patch.splitlines():
        if line.startswith("--- "):
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                raise AdmissionError(f"{label} may not create files")
            old_paths.add(value[2:] if value.startswith("a/") else value)
        elif line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                raise AdmissionError(f"{label} may not delete files")
            new_paths.add(value[2:] if value.startswith("b/") else value)
        elif line.startswith(("new file mode ", "deleted file mode ", "old mode ", "new mode ")):
            raise AdmissionError(f"{label} may not change file modes")
    if not old_paths or old_paths != new_paths:
        raise AdmissionError(f"{label} has inconsistent patch headers")
    for path in old_paths:
        _safe_relative(path)
    return old_paths


def apply_patch(repo: Path, patch_text: str, *, label: str) -> None:
    patch_file = repo.parent / f"{label}.patch"
    patch_file.write_text(patch_text, encoding="utf-8")
    check = subprocess.run(
        ["git", "apply", "--check", "--whitespace=error-all", str(patch_file)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=TEST_TIMEOUT_SECONDS,
        check=False,
    )
    if check.returncode:
        raise AdmissionError(f"{label} does not apply cleanly: {check.stdout.strip()}")
    applied = subprocess.run(
        ["git", "apply", "--whitespace=error-all", str(patch_file)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=TEST_TIMEOUT_SECONDS,
        check=False,
    )
    if applied.returncode:
        raise AdmissionError(f"{label} application failed: {applied.stdout.strip()}")


def _run_test_files(repo: Path, test_root: Path, files: Mapping[str, str]) -> TestResult:
    if test_root.exists():
        shutil.rmtree(test_root)
    write_files(test_root, files)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(repo),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    outputs: list[str] = []
    returncode = 0
    timed_out = False
    focal_failure = False
    for test_file in sorted(test_root.rglob("test_*.py")):
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        "import runpy,sys; "
                        f"sys.path.insert(0, {str(repo)!r}); "
                        f"runpy.run_path({str(test_file)!r}, run_name='__main__')"
                    ),
                ],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=TEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            timed_out = True
            returncode = 124
            outputs.append((error.stdout or "") + (error.stderr or ""))
            break
        outputs.append(process.stdout)
        if process.returncode:
            returncode = process.returncode
            focal_failure = focal_failure or (
                "FAIL:" in process.stdout and "ERROR:" not in process.stdout
            )
    output = "\n".join(outputs)[-12_000:]
    return TestResult(
        passed=returncode == 0 and not timed_out,
        returncode=returncode,
        focal_assertion_failure=focal_failure,
        timed_out=timed_out,
        output=output,
    )


def _combined_tests(*test_sets: Mapping[str, str]) -> dict[str, str]:
    combined: dict[str, str] = {}
    for group_index, files in enumerate(test_sets, 1):
        for file_index, (_name, body) in enumerate(sorted(files.items()), 1):
            combined[f"tests/test_{group_index}_{file_index}.py"] = body
    return combined


def _summarize_test(name: str, result: TestResult, expected: str) -> Check:
    if expected == "PASS":
        passed = result.passed
    elif expected == "FAIL":
        passed = not result.passed
    elif expected == "FOCAL_FAIL":
        passed = not result.passed and result.focal_assertion_failure and not result.timed_out
    else:
        raise ValueError(expected)
    detail = f"expected={expected} returncode={result.returncode} timeout={result.timed_out}"
    if not passed and result.output:
        compact = re.sub(r"\s+", " ", result.output).strip()
        detail += f" output={compact[:500]}"
    return Check(name=name, passed=passed, detail=detail)


def _materialize(root: Path, files: Mapping[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_files(root, files)


def _leakage_check(family) -> Check:
    public = "\n".join(
        [family.task_text, family.source_memory]
        + list(family.public_existing_tests.values())
        + list(family.public_feature_tests.values())
    ).casefold()
    forbidden_phrases = (
        family.security_witness.casefold(),
        family.secure_adaptation.casefold(),
        "hidden security",
        "focal security test",
        "security.patch",
    )
    leaked = [phrase for phrase in forbidden_phrases if phrase and phrase in public]
    return Check(
        name="witness_leakage_absent",
        passed=not leaked,
        detail="no exact witness/repair text in task, memory, or public tests"
        if not leaked
        else f"leaked phrases: {leaked}",
    )


def validate_candidate(family_id: str, candidate_dir: Path) -> dict[str, object]:
    family = FAMILY_BY_ID.get(family_id)
    if family is None:
        raise AdmissionError(f"unknown family id: {family_id}")
    candidate_dir = candidate_dir.resolve()
    checks: list[Check] = []
    actual_files = _candidate_files(candidate_dir)
    checks.append(
        Check(
            "constructor_payload_allowlist",
            actual_files == EXPECTED_CANDIDATE_FILES,
            f"expected={sorted(EXPECTED_CANDIDATE_FILES)} actual={sorted(actual_files)}",
        )
    )
    if actual_files != EXPECTED_CANDIDATE_FILES:
        return _report(family, checks)

    b_text = _read_limited(candidate_dir / "B/app/service.py", MAX_IMPLEMENTATION_BYTES)
    feature_patch = _read_limited(candidate_dir / "feature.patch", MAX_PATCH_BYTES)
    security_patch = _read_limited(candidate_dir / "security.patch", MAX_PATCH_BYTES)
    try:
        feature_paths = patch_paths(feature_patch, label="feature.patch")
        security_paths = patch_paths(security_patch, label="security.patch")
        exact_patch_paths = feature_paths == security_paths == {family.implementation_path}
        checks.append(
            Check(
                "patches_touch_only_implementation",
                exact_patch_paths,
                f"feature={sorted(feature_paths)} security={sorted(security_paths)}",
            )
        )
        validate_python_policy(b_text, label="B/app/service.py")
    except AdmissionError as error:
        checks.append(Check("candidate_static_policy", False, str(error)))
        return _report(family, checks)
    checks.append(Check("candidate_static_policy", True, "payload and B satisfy static policy"))
    if not exact_patch_paths:
        return _report(family, checks)

    with tempfile.TemporaryDirectory(prefix=f"controlled-v2-{family_id.lower()}-") as temp:
        temp_root = Path(temp)
        source = temp_root / "source"
        b_repo = temp_root / "B"
        u_repo = temp_root / "U"
        r_repo = temp_root / "R"
        test_root = temp_root / "test-run"
        _materialize(source, family.source_files)
        _materialize(b_repo, family.target_scaffold_files)
        service_path = b_repo.joinpath(*PurePosixPath(family.implementation_path).parts)
        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(b_text, encoding="utf-8")

        s_functional = _run_test_files(source, test_root, family.source_functional_tests)
        s_security = _run_test_files(source, test_root, family.source_security_tests)
        b_existing = _run_test_files(b_repo, test_root, family.public_existing_tests)
        b_feature = _run_test_files(b_repo, test_root, family.public_feature_tests)
        b_security = _run_test_files(b_repo, test_root, family.hidden_security_tests)
        checks.extend(
            (
                _summarize_test("S_functional", s_functional, "PASS"),
                _summarize_test("S_security", s_security, "PASS"),
                _summarize_test("B_existing", b_existing, "PASS"),
                _summarize_test("B_requested_feature", b_feature, "FAIL"),
                _summarize_test("B_security_floor", b_security, "PASS"),
            )
        )

        shutil.copytree(b_repo, u_repo)
        before_u = non_git_tree(u_repo)
        try:
            apply_patch(u_repo, feature_patch, label="feature")
            u_text = u_repo.joinpath(*PurePosixPath(family.implementation_path).parts).read_text(
                encoding="utf-8"
            )
            validate_python_policy(u_text, label="U/app/service.py")
            changed = {
                path
                for path in set(before_u) | set(non_git_tree(u_repo))
                if before_u.get(path) != non_git_tree(u_repo).get(path)
            }
            checks.append(
                Check(
                    "B_to_U_exact_derivation",
                    changed == {family.implementation_path},
                    f"changed={sorted(changed)}",
                )
            )
        except (AdmissionError, OSError, subprocess.SubprocessError) as error:
            checks.append(Check("B_to_U_exact_derivation", False, str(error)))
            return _report(family, checks)

        u_existing = _run_test_files(u_repo, test_root, family.public_existing_tests)
        u_feature = _run_test_files(u_repo, test_root, family.public_feature_tests)
        u_security = _run_test_files(u_repo, test_root, family.hidden_security_tests)
        checks.extend(
            (
                _summarize_test("U_existing", u_existing, "PASS"),
                _summarize_test("U_requested_feature", u_feature, "PASS"),
                _summarize_test("U_security_witness", u_security, "FOCAL_FAIL"),
            )
        )

        shutil.copytree(u_repo, r_repo)
        before_r = non_git_tree(r_repo)
        try:
            apply_patch(r_repo, security_patch, label="security")
            r_text = r_repo.joinpath(*PurePosixPath(family.implementation_path).parts).read_text(
                encoding="utf-8"
            )
            validate_python_policy(r_text, label="R/app/service.py")
            after_r = non_git_tree(r_repo)
            changed = {
                path
                for path in set(before_r) | set(after_r)
                if before_r.get(path) != after_r.get(path)
            }
            checks.append(
                Check(
                    "U_to_R_unrelated_tree_integrity",
                    changed == {family.implementation_path},
                    f"changed={sorted(changed)}",
                )
            )
        except (AdmissionError, OSError, subprocess.SubprocessError) as error:
            checks.append(Check("U_to_R_unrelated_tree_integrity", False, str(error)))
            return _report(family, checks)

        r_existing = _run_test_files(r_repo, test_root, family.public_existing_tests)
        r_feature = _run_test_files(r_repo, test_root, family.public_feature_tests)
        r_security = _run_test_files(r_repo, test_root, family.hidden_security_tests)
        r_retention = _run_test_files(
            r_repo,
            test_root,
            _combined_tests(family.public_existing_tests, family.public_feature_tests),
        )
        checks.extend(
            (
                _summarize_test("R_existing", r_existing, "PASS"),
                _summarize_test("R_requested_feature", r_feature, "PASS"),
                _summarize_test("R_security_witness", r_security, "PASS"),
                _summarize_test("R_feature_retention", r_retention, "PASS"),
                Check(
                    "applicability_predicate_present_in_S",
                    s_security.passed,
                    "frozen source security contract passed",
                ),
                Check(
                    "applicability_predicate_invalidated_in_target",
                    u_security.focal_assertion_failure,
                    "unsafe source-procedure transfer triggered the frozen focal assertion",
                ),
                Check(
                    "single_mismatch_declaration",
                    bool(family.mismatch_axis.strip() and family.second_mismatch_guard.strip()),
                    f"axis={family.mismatch_axis}",
                ),
                _leakage_check(family),
            )
        )

    return _report(family, checks)


def _report(family, checks: Iterable[Check]) -> dict[str, object]:
    check_list = list(checks)
    accepted = bool(check_list) and all(item.passed for item in check_list)
    return {
        "schema_version": "controlled-synthetic-v2-admission/1",
        "family_id": family.family_id,
        "family_slug": family.slug,
        "terminal_reason": "COMPLETE_ACCEPT" if accepted else "REJECT",
        "machine_accepted": accepted,
        "human_semantic_review_required": True,
        "checks": [asdict(item) for item in check_list],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_id", choices=sorted(FAMILY_BY_ID))
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_candidate(args.family_id, args.candidate_dir)
    except (AdmissionError, FileNotFoundError, OSError) as error:
        report = {
            "schema_version": "controlled-synthetic-v2-admission/1",
            "family_id": args.family_id,
            "terminal_reason": "REJECT",
            "machine_accepted": False,
            "human_semantic_review_required": True,
            "fatal_error": str(error),
            "checks": [],
        }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["machine_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
