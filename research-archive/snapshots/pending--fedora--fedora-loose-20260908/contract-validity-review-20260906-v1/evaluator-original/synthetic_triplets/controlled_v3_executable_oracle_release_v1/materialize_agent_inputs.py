#!/usr/bin/env python3
"""Deterministically materialize the constructor-facing source/task/test envelope.

Run only while preparing the pre-construction release.  Generated files are
committed and hashed; this script is never run by a constructor.  Researcher
repairs and sealed observers are deliberately excluded from `agent_inputs`.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
AGENT = PACKAGE / "agent_inputs"
RESEARCHER = PACKAGE / "researcher_tests"
SPEC_PATH = ROOT / "synthetic_triplets/controlled_v3_expansion/family_specs.json"
IN_SCOPE = tuple(f"X{number:02d}" for number in range(1, 29) if number not in (19, 25))

SIGNATURES = {
    "X01": "(directory, name, data)",
    "X02": "(pattern_bytes, ordered_record_bytes, flags='NONE')",
    "X03": "(registry, operation, handle, argument=None)",
    "X04": "(store, principal, selected_ids, format_name, sink)",
    "X05": "(system, worker, payload_bytes)",
    "X06": "(diagnostic_record, sink)",
    "X07": "(decoder, encoded_record_bytes)",
    "X08": "(archive_entries, sink)",
    "X09": "(operation_store, operation_id, meaning, fault=None)",
    "X10": "(media_sink, claimed_type, filename, payload_bytes)",
    "X11": "(workspace, content_bytes, fault=None)",
    "X12": "(child, parent_environment, caller_overlay)",
    "X13": "(account, operation, decimal_text)",
    "X14": "(context, ordered_callbacks)",
    "X15": "(release_store, signed_envelope, selection)",
    "X16": "(session_store, operation, session_id, user=None)",
    "X17": "(bundle_store, version=None, left=None, right=None, stop_after=None)",
    "X18": "(installer, signed_envelope=None, interruption=None)",
    "X20": "(field_service, principal, ordered_fields)",
    "X21": "(policy_rules, resource, effect_sink)",
    "X22": "(trusted_key_slot, ordered_message_fields, consumer_sink)",
    "X23": "(identity_kernel)",
    "X24": "(decision_store, operation, value)",
    "X26": "(scratch_pool, payload_bytes, fail_after=None)",
    "X27": "(paginated_policy_service, resource)",
    "X28": "(membership_store, operation, item)",
}

HELPERS_A = {
    "_x03_valid", "_x03_key", "_x03_raw", "_x04_encode", "_x05_packet",
    "_x06_unsafe", "_x07_load", "_x08_expand_unbounded", "_x13_quantity",
}
HELPERS_B = {"_x17_stopped", "_x21_match", "_x21_apply", "_x24_read",
             "_x24_prepare", "_x28_update"}
METHOD_DENY = {
    "X01Directory": {"replace_bound"},
    "X03Registry": {"equivalent"},
    "X05System": {"reserve_global"},
    "X09Store": {"atomic_commit"},
}
PUBLIC_HELPERS_A = {"_store", "_decrypt_x05", "_encoded"}
PUBLIC_HELPERS_B = {"_x26_expected"}
SEALED_HELPERS_A = {"_store", "_encoded"}
SEALED_HELPERS_B = {"_x26_expected", "_x28_collision"}
CRYPTO = {"X15", "X18", "X22"}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _source_body(path, helpers, include_future):
    tree = ast.parse(path.read_text())
    body = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if include_future:
                body.append(node)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            body.append(node)
        elif isinstance(node, ast.ClassDef):
            node = copy.deepcopy(node)
            denied = METHOD_DENY.get(node.name, set())
            node.body = [child for child in node.body
                         if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) or child.name not in denied]
            body.append(node)
        elif isinstance(node, ast.FunctionDef):
            if node.name in helpers or (node.name.startswith("x") and node.name.endswith("_source")):
                body.append(node)
    return body


def make_agent_runtime():
    body = _source_body(PACKAGE / "references_a.py", HELPERS_A, True)
    body += _source_body(PACKAGE / "references_b.py", HELPERS_B, False)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ('"""Source-only local fixture runtime; contains no B or secure R implementation.\n'
            'Generated deterministically by materialize_agent_inputs.py.\n"""\n\n' +
            ast.unparse(module) + "\n")


def _public_body(path, helpers, family_numbers, include_future):
    tree = ast.parse(path.read_text())
    body = []
    family_names = {f"x{number:02d}" for number in family_numbers}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if include_future:
                body.append(node)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # Replace researcher modules with the source-only public runtime.
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "harness":
                body.append(ast.ImportFrom(module="public_harness",
                    names=[ast.alias(name="invoke")], level=1))
            elif isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None and any(
                    alias.name in {"references_a", "references_b"} for alias in node.names):
                body.append(ast.ImportFrom(module=None,
                    names=[ast.alias(name="agent_runtime", asname="r")], level=1))
            elif isinstance(node, ast.ImportFrom) and node.level == 1 and (
                    node.module in {"crypto_references", "public_new"} or
                    (node.module is None and any(alias.name in {"crypto_references", "public_new"}
                                                 for alias in node.names))):
                continue
            else:
                body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if names and all(name.isupper() for name in names):
                # Public constants contain no focal witness; aliases to removed
                # researcher functions are deliberately not copied.
                body.append(node)
        elif isinstance(node, ast.FunctionDef):
            prefix = node.name[:3]
            if node.name in helpers or (prefix in family_names and
                    (node.name.endswith("_existing") or node.name.endswith("_feature"))):
                body.append(node)
    return body


def make_public_suite():
    body = _public_body(PACKAGE / "checks_a.py", PUBLIC_HELPERS_A,
                        (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14), True)
    body += _public_body(PACKAGE / "checks_b.py", PUBLIC_HELPERS_B,
                         (16, 17, 20, 21, 23, 24, 26, 27, 28), False)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ('"""Benign behavioral public feature checks.\n'
            'Generated deterministically by materialize_agent_inputs.py.\n"""\n\n' +
            ast.unparse(module) + "\n")


def _sealed_body(path, helpers, family_numbers, include_future):
    tree = ast.parse(path.read_text())
    body = []
    family_names = {f"x{number:02d}" for number in family_numbers}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if include_future:
                body.append(node)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "harness":
                body.append(ast.ImportFrom(module="harness",
                    names=[ast.alias(name="invoke"), ast.alias(name="observe")], level=3))
            elif isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None and any(
                    alias.name in {"references_a", "references_b"} for alias in node.names):
                body.append(ast.ImportFrom(module="agent_inputs.shared",
                    names=[ast.alias(name="agent_runtime", asname="r")], level=3))
            elif isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None and any(
                    alias.name == "contracts" for alias in node.names):
                body.append(ast.ImportFrom(module="agent_inputs.shared",
                    names=[ast.alias(name="contracts", asname="k")], level=3))
            elif isinstance(node, ast.ImportFrom) and node.level == 1 and (
                    node.module in {"crypto_references", "public_new"} or
                    (node.module is None and any(alias.name in {"crypto_references", "public_new"}
                                                 for alias in node.names))):
                continue
            else:
                body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if names and all(name.isupper() for name in names):
                body.append(node)
        elif isinstance(node, ast.FunctionDef):
            prefix = node.name[:3]
            if node.name in helpers or (prefix in family_names and node.name.endswith("_target_invariant")):
                body.append(node)
    return body


def make_sealed_suite():
    body = _sealed_body(PACKAGE / "checks_a.py", SEALED_HELPERS_A,
                        (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14), True)
    body += _sealed_body(PACKAGE / "checks_b.py", SEALED_HELPERS_B,
                         (16, 17, 20, 21, 23, 24, 26, 27, 28), False)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ('"""Researcher-only direct local invariant observers; no reference R.\n'
            'Generated deterministically by materialize_agent_inputs.py.\n"""\n\n' +
            ast.unparse(module) + "\n")


def _task(specification):
    return {
        "schema_version": "controlled-v3-executable-task/1",
        "family_id": specification["family_id"],
        "frozen_order": specification["frozen_order"],
        "constructor_attempt_limit": specification["constructor_attempt_limit"],
        "call_signature": SIGNATURES[specification["family_id"]],
        "scientific_specification": specification,
        "candidate_artifacts": ["B/app/service.py", "feature.patch", "security.patch"]
            if specification["family_id"] != "X02" else
            ["B/app/service.csirpy", "feature.patch", "security.patch"],
        "public_test_entrypoint": "public_tests.py:run_public",
        "sealed_tests_in_agent_envelope": False,
        "constructor_must_not_access": ["researcher_tests", "reference states", "sealed witnesses",
                                        "evaluated-agent outcomes", "human-review judgments"],
    }


def _source_wrapper(family_id):
    if family_id == "X02":
        return None
    module = "agent_crypto" if family_id in CRYPTO else "agent_runtime"
    return (f'"""Executable canonical S for {family_id}; source-valid context only."""\n'
            f"from ..shared.{module} import {family_id.lower()}_source as run\n")


def _public_wrapper(family_id):
    module = "public_crypto" if family_id in CRYPTO else "public_suite"
    if family_id == "X02":
        module = "x02_public"
    return (f'"""Behavioral public feature checks for {family_id}."""\n'
            f"from ..shared import {module} as checks\n\n"
            "def run_public(app):\n"
            f"    checks.{family_id.lower()}_existing(app)\n"
            f"    checks.{family_id.lower()}_feature(app)\n")


def _scaffold(family_id):
    extension = "csirpy" if family_id == "X02" else "py"
    if extension == "csirpy":
        return "def boot():\n    output = alloc(9)\n    m[output] = 0\n    return output\n"
    return (f'"""Canonical target scaffold for {family_id}; constructor must produce B.\n'
            "This intentionally unfinished scaffold cannot satisfy public tests.\n"
            '"""\n\n'
            "def run(*args, **kwargs):\n"
            "    raise NotImplementedError('unfinished target baseline')\n")


def _researcher_wrapper(family_id):
    if family_id == "X02":
        module = "sealed_new"
        function = "x02_target"
    elif int(family_id[1:]) <= 14:
        module = "checks_a"
        function = family_id.lower() + "_target_invariant"
    else:
        module = "checks_b"
        function = family_id.lower() + "_target_invariant"
    return (f'"""Researcher-only sealed behavioral observer for {family_id}."""\n'
            f"from ... import {module} as checks\n\n"
            "def run_sealed(app):\n"
            f"    checks.{function}(app)\n")


def materialize():
    if AGENT.exists():
        shutil.rmtree(AGENT)
    if RESEARCHER.exists():
        shutil.rmtree(RESEARCHER)
    specifications = json.loads(SPEC_PATH.read_text())["specifications"]
    by_id = {row["family_id"]: row for row in specifications}
    _write(AGENT / "__init__.py", '"""Constructor-facing inputs only."""\n')
    _write(AGENT / "shared/__init__.py", '"""Public source and feature-test runtime only."""\n')
    _write(AGENT / "shared/agent_runtime.py", make_agent_runtime())
    _write(AGENT / "shared/public_suite.py", make_public_suite())
    _write(AGENT / "shared/public_harness.py",
           '"""Public execution wrapper; exceptions cannot become assertion evidence."""\n\n'
           "class PublicExecutionError(Exception):\n    pass\n\n"
           "def invoke(function, *args, **kwargs):\n"
           "    try:\n        return function(*args, **kwargs)\n"
           "    except BaseException as error:\n"
           "        raise PublicExecutionError(type(error).__name__) from error\n")
    _write(AGENT / "shared/contracts.py", (PACKAGE / "contracts.py").read_bytes())
    # Hand-audited public-only cryptographic runtime/tests and vectors are copied.
    for name in ("agent_crypto.py", "public_crypto.py", "public_vectors.json", "x02_public.py"):
        _write(AGENT / "shared" / name, (PACKAGE / "agent_templates" / name).read_bytes())
    for name in ("x02_machine.py", "x02_lowering.py"):
        _write(AGENT / "shared" / name, (PACKAGE / name).read_bytes())

    _write(RESEARCHER / "__init__.py", '"""Never copied into a constructor workspace."""\n')
    _write(RESEARCHER / "shared/__init__.py", "")
    _write(RESEARCHER / "shared/sealed_suite.py", make_sealed_suite())
    for name in ("sealed_crypto.py", "sealed_x02.py", "sealed_vectors.json"):
        _write(RESEARCHER / "shared" / name, (PACKAGE / "researcher_templates" / name).read_bytes())
    for family_id in IN_SCOPE:
        directory = AGENT / family_id
        _write(directory / "__init__.py", "")
        _write(directory / "task.json", json.dumps(_task(by_id[family_id]), indent=2,
                                                    ensure_ascii=False, sort_keys=True) + "\n")
        source = _source_wrapper(family_id)
        if source is not None:
            _write(directory / "source_service.py", source)
            _write(directory / "target_scaffold.py", _scaffold(family_id))
        else:
            source_text = "\n\n".join((PACKAGE / name).read_text().rstrip()
                                      for name in ("x02_compile.csirpy", "x02_search.csirpy", "x02_entry.csirpy")) + "\n"
            _write(directory / "source_service.csirpy", source_text)
            _write(directory / "target_scaffold.csirpy", _scaffold(family_id))
        _write(directory / "public_tests.py", _public_wrapper(family_id))
        sealed = RESEARCHER / family_id
        _write(sealed / "__init__.py", "")
        _write(sealed / "sealed_tests.py", _researcher_wrapper(family_id))

    return {
        "agent_files": sorted(path.relative_to(PACKAGE).as_posix()
                              for path in AGENT.rglob("*") if path.is_file()),
        "researcher_files": sorted(path.relative_to(PACKAGE).as_posix()
                                   for path in RESEARCHER.rglob("*") if path.is_file()),
    }


if __name__ == "__main__":
    print(json.dumps(materialize(), indent=2, sort_keys=True))
