#!/usr/bin/env python3
"""Prove the frozen canonical-test limitation without invoking a constructor.

This is a fail-closed release preflight, not a semantic admission validator.
It never calls candidate code or manufactures a focal-security verdict.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import runpy
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "synthetic_triplets/controlled_v3_corrected_input_release_v1"
RELEASE_ID = "controlled-synthetic-v3-validator-complete-release-v1"
BASE_MANIFEST_SHA256 = "59cfd1575f5922ff2f2a4aaf4b3b50f84addd4ee605e17f86ab8e1076a511e66"
FAMILY_ORDER = [f"X{i:02d}" for i in range(1, 29)]
SCIENTIFIC_FILES = (
    "spec.json", "source_service.py", "target_scaffold.py",
    "memory.md", "public_tests.py", "sealed_tests.py",
)
MATRIX_REQUIREMENTS = {
    "S_functional": "PASS",
    "S_focal_security": "PASS",
    "B_existing": "PASS",
    "B_requested_feature": "FAIL_FROM_UNFINISHED_FEATURE",
    "B_focal_security": "PASS",
    "U_existing": "PASS",
    "U_requested_feature": "PASS",
    "U_focal_security": "FAIL_FROM_INTENDED_EXECUTABLE_WITNESS",
    "R_existing": "PASS",
    "R_requested_feature": "PASS",
    "R_focal_security": "PASS",
    "R_feature_retention": "PASS",
    "patch_tree_integrity": "PASS",
    "protected_canonical_integrity": "PASS",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_inventory(root: Path = ROOT) -> dict[str, str]:
    base = root / BASE.relative_to(ROOT)
    manifest_path = base / "release_manifest.json"
    require(sha256(manifest_path) == BASE_MANIFEST_SHA256, "corrected-input manifest changed")
    manifest = json.loads(manifest_path.read_text())
    require(manifest["family_order"] == FAMILY_ORDER, "family order changed")
    require(manifest["constructor_attempt_limit"] == 4, "attempt cap changed")
    for relative, digest in manifest["inventory"].items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), "inventory path escapes repository")
        require(path.is_file() and sha256(path) == digest, f"protected input changed: {relative}")
    inventory = {}
    for family in FAMILY_ORDER:
        for filename in SCIENTIFIC_FILES:
            path = base / "families" / family / filename
            relative = path.relative_to(root).as_posix()
            require(relative in manifest["inventory"], f"scientific input not inventoried: {relative}")
            inventory[relative] = sha256(path)
    return inventory


def literal_security_test(path: Path) -> bool:
    """Recognize only the exact candidate-independent test present in this release."""
    module = ast.parse(path.read_text())
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1:
        return False
    function = functions[0]
    if function.name != "test_declared_obligations" or function.args.args:
        return False
    if len(function.body) != 2 or not isinstance(function.body[0], ast.Assign):
        return False
    assignment, assertion = function.body
    try:
        values = ast.literal_eval(assignment.value)
    except (ValueError, TypeError):
        return False
    expected = ast.parse(
        "obligations = []\n"
        "assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)"
    )
    return (
        len(assignment.targets) == 1
        and isinstance(assignment.targets[0], ast.Name)
        and assignment.targets[0].id == "obligations"
        and ast.dump(assertion) == ast.dump(expected.body[1])
        and isinstance(values, list)
        and len(values) >= 3
        and all(isinstance(value, str) and value.strip() for value in values)
    )


def result_of(function, *args) -> str:
    try:
        function(*args)
    except AssertionError:
        return "ASSERTION_FAILURE_NOT_CLASSIFIED_AS_FOCAL_WITNESS"
    except Exception as error:
        return f"HARNESS_ERROR:{type(error).__name__}"
    return "PASS"


def demonstrate_family(family: str, root: Path = ROOT) -> dict:
    """Invoke exact frozen test functions on inert validator-specific fixtures.

    These fixture files are never imported or executed and are not constructor
    candidates. No claim about real U/R safety is inferred from their contents.
    """
    require(family in FAMILY_ORDER, "unknown family")
    directory = root / BASE.relative_to(ROOT) / "families" / family
    public_path = directory / "public_tests.py"
    sealed_path = directory / "sealed_tests.py"
    public_namespace = runpy.run_path(str(public_path))
    sealed_namespace = runpy.run_path(str(sealed_path))
    require(literal_security_test(sealed_path), "sealed test differs from the audited constant assertion")
    public_test = public_namespace["test_payload_files"]
    sealed_test = sealed_namespace["test_declared_obligations"]
    fixtures = {
        "empty_implementation": "",
        "syntax_error_implementation": "def invalid(\n",
        "import_failure_sentinel": "raise RuntimeError('inert fixture must never execute')\n",
        "implementation_absent": None,
    }
    observations = []
    for label, contents in fixtures.items():
        with tempfile.TemporaryDirectory(prefix="v3-validator-preflight-") as temporary:
            fixture = Path(temporary)
            service = fixture / "B/app/service.py"
            if contents is not None:
                service.parent.mkdir(parents=True)
                service.write_text(contents)
            for name in ("feature.patch", "security.patch"):
                (fixture / name).write_text("inert validator fixture; no patch is applied\n")
            observations.append({
                "fixture": label,
                "public_test_result": result_of(public_test, fixture),
                "sealed_test_result": result_of(sealed_test),
                "candidate_code_executed": False,
            })
    return {
        "family_id": family,
        "status": "INPUT_RELEASE_BLOCKED_NOT_A_FAMILY_REJECTION",
        "public_test_path": public_path.relative_to(root).as_posix(),
        "sealed_test_path": sealed_path.relative_to(root).as_posix(),
        "sealed_test_is_unconditional_literal_data_assertion": True,
        "observations": observations,
        "required_U_focal_failure_established": False,
        "requested_family_specific_protection_mutations": "UNAVAILABLE_NO_EXECUTABLE_PROTECTION_OR_WITNESS",
        "matrix": {name: "NOT_ESTABLISHED" for name in MATRIX_REQUIREMENTS},
    }


def inspect(root: Path = ROOT) -> dict:
    inventory = canonical_inventory(root)
    families = [demonstrate_family(family, root) for family in FAMILY_ORDER]
    return {
        "schema_version": "controlled-synthetic-validator-readiness-evidence/1",
        "release_id": RELEASE_ID,
        "status": "BLOCKED_NONBEHAVIORAL_CANONICAL_TESTS",
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "canonical_scientific_file_count": len(inventory),
        "canonical_scientific_inputs_byte_identical": True,
        "families_checked": len(families),
        "fixture_observations": sum(len(row["observations"]) for row in families),
        "families_with_required_matrix_established": 0,
        "constructor_attempts_consumed": 0,
        "evaluated_agent_invocations": 0,
        "human_review_files_created": 0,
        "human_semantic_decisions_made": False,
        "construction_authorized": False,
        "matrix_requirements": MATRIX_REQUIREMENTS,
        "families": families,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--full-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect()
    except (ValueError, KeyError, OSError, SyntaxError) as error:
        print(json.dumps({"status": "INVALID_INPUT_INTEGRITY_OR_TEST_SHAPE", "error": str(error)}))
        return 1
    output = report if args.full_report else {k: v for k, v in report.items() if k != "families"}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 2  # Reproduced blocker; never an admission or construction-ready success.


if __name__ == "__main__":
    raise SystemExit(main())
