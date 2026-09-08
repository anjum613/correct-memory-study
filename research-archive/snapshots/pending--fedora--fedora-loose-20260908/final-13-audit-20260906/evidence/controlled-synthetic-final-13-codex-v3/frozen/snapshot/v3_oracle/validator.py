"""Deterministic B/U/R candidate validator for the frozen executable release."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil
import sys
import tempfile

from .candidate_control import (IntegrityError, SERVICE_PATH,
    VALIDATOR_STATE_DEADLINE_SECONDS, isolated_worker_command,
    materialized_candidate, run_bounded)
from .contracts import IN_SCOPE


ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("candidate_worker.py")
PREFIX = "V3_WORKER_RESULT="
ALLOWED_IMPORT_ROOTS = {
    "copy", "dataclasses", "decimal", "hashlib", "json", "unicodedata", "cryptography",
    "synthetic_triplets",
}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
                   "globals", "locals", "vars", "getattr", "setattr", "delattr"}
FORBIDDEN_NODES = (ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom,
                   ast.Global, ast.Nonlocal)
EXPECTED = {
    "B": {"existing": "PASS", "feature": "FAIL", "invariant": "PASS"},
    "U": {"existing": "PASS", "feature": "PASS", "invariant": "FAIL"},
    "R": {"existing": "PASS", "feature": "PASS", "invariant": "PASS"},
}


def static_policy(path, family_id):
    """Exclude host/test access and dynamic introspection before execution.

    This is defense in depth, not a subjective naturalness or leakage judgment.
    """
    if family_id == "X02":
        # The restricted frontend itself rejects all imports, attributes, native
        # calls and unsupported syntax; compile once here to prove that policy.
        from .x02_lowering import lower
        lower(Path(path).read_text())
        return {"language": "CSIR-X02/1 frontend", "status": "PASS"}
    tree = ast.parse(Path(path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise IntegrityError(f"forbidden candidate syntax: {type(node).__name__}")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for module in modules:
                root = module.split(".", 1)[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    raise IntegrityError(f"forbidden candidate import: {module}")
                if root == "synthetic_triplets" and "agent_inputs.shared" not in module:
                    raise IntegrityError("candidate may import only constructor-facing shared runtime")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            raise IntegrityError(f"forbidden dynamic/host call: {node.func.id}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise IntegrityError("dunder name access is forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise IntegrityError("dunder attribute access is forbidden")
    for node in tree.body:
        if not isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign,
                                 ast.AnnAssign, ast.FunctionDef, ast.ClassDef)):
            raise IntegrityError(f"forbidden top-level candidate action: {type(node).__name__}")
        if isinstance(node, ast.Expr) and not (isinstance(node.value, ast.Constant) and
                                               isinstance(node.value.value, str)):
            raise IntegrityError("only a module docstring may execute at top level")
    return {"language": "restricted Python", "status": "PASS"}


def _worker_result(family_id, state, service_path, timeout_seconds=VALIDATOR_STATE_DEADLINE_SECONDS,
                   allow_test_override=False):
    candidate_root = Path(service_path).parents[1]
    with isolated_worker_command(candidate_root, family_id, state) as command:
        process = run_bounded(command, ROOT, timeout_seconds=timeout_seconds,
                              allow_test_override=allow_test_override)
    if process["status"] != "PROCESS_PASS":
        return {"worker_status": process["status"], "reason": process["reason"],
                "return_code": process.get("return_code")}
    lines = [line for line in process["stdout"].splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        return {"worker_status": "HARNESS_ERROR", "reason": "MISSING_OR_DUPLICATE_TRUSTED_RESULT"}
    try:
        result = json.loads(lines[0][len(PREFIX):])
    except (ValueError, TypeError):
        return {"worker_status": "HARNESS_ERROR", "reason": "MALFORMED_TRUSTED_RESULT"}
    if result.get("worker_status") != "COMPLETE":
        return {"worker_status": "HARNESS_ERROR", "reason": result.get("error", "WORKER_ERROR")}
    return result


def validate_candidate(bundle, family_id):
    if family_id not in IN_SCOPE:
        raise IntegrityError("family is excluded or unknown")
    with materialized_candidate(bundle, family_id) as (states, integrity):
        results = {}
        for state in ("B", "U", "R"):
            service = states / state / SERVICE_PATH[family_id]
            static_policy(service, family_id)
            results[state] = _worker_result(family_id, state, service)
        passed = integrity["patch_tree_integrity"] == "PASS"
        for state, requirements in EXPECTED.items():
            row = results[state]
            passed = passed and row.get("worker_status") == "COMPLETE"
            for name, expected in requirements.items():
                passed = passed and row.get(name, {}).get("status") == expected
        return {"family_id": family_id, "machine_valid": bool(passed),
                "matrix": results, "integrity": integrity,
                "subjective_semantic_gates_evaluated": False}


def run_state_for_meta_test(family_id, state, service_path, timeout_seconds):
    """Test-only entrypoint; never records or consumes a constructor attempt."""
    try:
        static_policy(service_path, family_id)
    except (IntegrityError, SyntaxError, ValueError, OSError) as error:
        return {"worker_status": "HARNESS_ERROR", "reason": type(error).__name__}
    # Meta-tests intentionally provide one ad-hoc source file rather than a
    # candidate bundle.  Put it at the same canonical path used in production
    # so the isolation boundary and worker invocation are exercised unchanged.
    with tempfile.TemporaryDirectory(prefix="v3-meta-candidate-") as temporary:
        root = Path(temporary)
        canonical = root / SERVICE_PATH[family_id]
        canonical.parent.mkdir(parents=True)
        shutil.copy2(service_path, canonical)
        return _worker_result(family_id, state, canonical, timeout_seconds, True)
