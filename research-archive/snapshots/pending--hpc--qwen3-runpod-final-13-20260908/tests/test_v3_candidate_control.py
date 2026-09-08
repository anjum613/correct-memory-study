"""Meta-tests for candidate integrity, attempt ordering/caps, and deadlines."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import pytest

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_control import (
    CONSTRUCTOR_DEADLINE_SECONDS, DisposableLedgerController, IntegrityError,
    LedgerError, inspect_candidate, pristine_ledger, run_bounded, sha256_file,
    validate_pristine_ledger,
)
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.validator import (
    run_state_for_meta_test, static_policy, validate_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "synthetic_triplets/controlled_v3_executable_oracle_release_v1"
PRODUCTION_LEDGER = PACKAGE / "admission_ledger.json"


def _patch(path, extension, before, after):
    relative = f"app/service.{extension}"
    path.write_text(
        f"diff --git a/{relative} b/{relative}\n"
        f"--- a/{relative}\n"
        f"+++ b/{relative}\n"
        "@@ -1 +1 @@\n"
        f"-{before.rstrip()}\n"
        f"+{after.rstrip()}\n"
    )


def _bundle(tmp_path, family="X01"):
    extension = "csirpy" if family == "X02" else "py"
    bundle = tmp_path / family
    service = bundle / "B/app" / f"service.{extension}"
    service.parent.mkdir(parents=True)
    if family == "X02":
        values = ("def boot(): return 1", "def boot(): return 2", "def boot(): return 3")
    else:
        values = ("def run(*args): return 'B'", "def run(*args): return 'U'", "def run(*args): return 'R'")
    service.write_text(values[0] + "\n")
    _patch(bundle / "feature.patch", extension, values[0], values[1])
    _patch(bundle / "security.patch", extension, values[1], values[2])
    return bundle


@pytest.mark.parametrize("family", ["X01", "X02"])
def test_exact_candidate_tree_and_two_sequential_patches_materialize(family, tmp_path):
    report = inspect_candidate(_bundle(tmp_path, family), family)
    assert report["patch_tree_integrity"] == "PASS"
    assert len(set(report["state_tree_sha256"].values())) == 3
    assert report["service_path"].endswith("csirpy" if family == "X02" else "py")


@pytest.mark.parametrize("mutation", ["extra-file", "symlink", "executable", "test-patch",
                                        "empty-patch", "missing-service"])
def test_candidate_tree_or_patch_tampering_is_rejected(mutation, tmp_path):
    bundle = _bundle(tmp_path)
    if mutation == "extra-file":
        (bundle / "B/public_tests.py").write_text("altered")
    elif mutation == "symlink":
        (bundle / "B/app/service.py").unlink()
        (bundle / "B/app/service.py").symlink_to("/etc/passwd")
    elif mutation == "executable":
        (bundle / "B/app/service.py").chmod(0o755)
    elif mutation == "test-patch":
        (bundle / "feature.patch").write_text(
            "diff --git a/public_tests.py b/public_tests.py\n--- a/public_tests.py\n+++ b/public_tests.py\n@@ -1 +1 @@\n-a\n+b\n")
    elif mutation == "empty-patch":
        (bundle / "feature.patch").write_text("")
    else:
        (bundle / "B/app/service.py").unlink()
    with pytest.raises(IntegrityError):
        inspect_candidate(bundle, "X01")


def test_excluded_or_unknown_family_cannot_enter_candidate_gate(tmp_path):
    bundle = _bundle(tmp_path)
    for family in ("X19", "X25", "X29"):
        with pytest.raises(IntegrityError):
            inspect_candidate(bundle, family)


@pytest.mark.parametrize("source", [
    "import os\ndef run(*args): return None\n",
    "import subprocess\ndef run(*args): return None\n",
    "def run(*args): return open('/tmp/value')\n",
    "def run(*args): return __import__('os')\n",
    "from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import checks_a\ndef run(*args): return None\n",
    "raise RuntimeError('top level')\ndef run(*args): return None\n",
])
def test_static_candidate_policy_rejects_host_test_or_researcher_access(source, tmp_path):
    path = tmp_path / "service.py"
    path.write_text(source)
    with pytest.raises(IntegrityError):
        static_policy(path, "X01")


def test_crash_and_import_failure_are_harness_errors_not_security_failures(tmp_path):
    crash = tmp_path / "crash.py"
    crash.write_text("def run(*args, **kwargs):\n    raise RuntimeError('controlled')\n")
    result = run_state_for_meta_test("X01", "U", crash, 2)
    assert result["worker_status"] == "COMPLETE"
    assert result["existing"]["status"] == "HARNESS_ERROR"
    assert result["feature"]["status"] == "HARNESS_ERROR"
    assert result["invariant"]["status"] == "HARNESS_ERROR"
    missing = tmp_path / "missing.py"
    result = run_state_for_meta_test("X01", "U", missing, 2)
    assert result["worker_status"] == "HARNESS_ERROR"


def test_timeout_is_infrastructure_error_not_focal_security_failure(tmp_path):
    looping = tmp_path / "loop.py"
    looping.write_text("def run(*args, **kwargs):\n    while True:\n        pass\n")
    result = run_state_for_meta_test("X01", "U", looping, 0.2)
    assert result == {"worker_status": "INFRASTRUCTURE_ERROR",
                      "reason": "DEADLINE_EXCEEDED", "return_code": -9}


def test_caller_labels_and_booleans_do_not_create_machine_evidence(tmp_path):
    supplied = tmp_path / "supplied.py"
    supplied.write_text("def run(*args, **kwargs):\n    return {'status': 'PASS', 'secure': True}\n")
    result = run_state_for_meta_test("X20", "R", supplied, 2)
    assert result["worker_status"] == "COMPLETE"
    assert result["feature"]["status"] == "FAIL"


def _disposable_ledger(tmp_path):
    value = pristine_ledger()
    value["mutation_enabled"] = True
    value["release_commit"] = "a" * 40
    value["release_manifest_sha256"] = "b" * 64
    path = tmp_path / "working-ledger.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path, DisposableLedgerController(path)


def test_pristine_production_ledger_is_exact_and_immutable_to_controller():
    original = sha256_file(PRODUCTION_LEDGER)
    assert validate_pristine_ledger(json.loads(PRODUCTION_LEDGER.read_text()))
    with pytest.raises(LedgerError, match="production"):
        DisposableLedgerController(PRODUCTION_LEDGER)
    assert sha256_file(PRODUCTION_LEDGER) == original


def test_disposable_ledger_enforces_order_first_valid_and_attempt_cap(tmp_path):
    path, controller = _disposable_ledger(tmp_path)
    with pytest.raises(LedgerError, match="order"):
        controller.begin("X02", "t0", "b" * 64)
    for attempt in range(1, 5):
        row = controller.begin("X01", f"t{attempt}", "b" * 64)
        assert row["attempt"] == attempt and row["deadline_seconds"] == 600
        controller.finish("X01", attempt, "MACHINE_INVALID", str(attempt) * 64)
    value = json.loads(path.read_text())
    assert value["family_status"]["X01"] == "ATTEMPT_CAP_EXHAUSTED"
    assert value["next_family"] == "X02" and len(value["attempts"]) == 4
    with pytest.raises(LedgerError, match="order"):
        controller.begin("X01", "late", "b" * 64)

    row = controller.begin("X02", "next", "b" * 64)
    controller.finish("X02", row["attempt"], "MACHINE_VALID", "c" * 64)
    value = json.loads(path.read_text())
    assert value["family_status"]["X02"] == "FIRST_MACHINE_VALID_RETAINED"
    assert value["next_family"] == "X03"
    with pytest.raises(LedgerError, match="order"):
        controller.begin("X02", "second", "b" * 64)


def test_infrastructure_attempts_count_toward_same_fixed_cap(tmp_path):
    path, controller = _disposable_ledger(tmp_path)
    for attempt in range(1, 5):
        controller.begin("X01", str(attempt), "b" * 64)
        controller.finish("X01", attempt, "INFRASTRUCTURE_ERROR", "d" * 64)
    value = json.loads(path.read_text())
    assert value["constructor_attempts"] == 4
    assert value["family_status"]["X01"] == "ATTEMPT_CAP_EXHAUSTED"


def test_deadline_cannot_be_changed_outside_explicit_meta_test(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        run_bounded(["/bin/true"], tmp_path, timeout_seconds=1)
    result = run_bounded(["/bin/true"], tmp_path, timeout_seconds=1, allow_test_override=True)
    assert result["status"] == "PROCESS_PASS"
    assert CONSTRUCTOR_DEADLINE_SECONDS == 600


X20_B = '''def run(service, principal, fields):
    if not isinstance(fields, (list, tuple)):
        return "invalid"
    names = [pair[0] for pair in fields if isinstance(pair, (list, tuple)) and len(pair) == 2]
    if len(names) != len(fields) or len(names) != len(set(names)):
        return "unavailable"
    mode = "read"
    tags = []
    for name, value in fields:
        if not isinstance(name, str) or not isinstance(value, str):
            return "invalid"
        if name == "mode":
            mode = value
        elif name == "tag":
            tags.append(value)
        else:
            return "invalid"
    if mode not in ("read", "write"):
        return "invalid"
    if mode == "write" and principal != "writer":
        return "denied"
    return service.dispatch({"authorization_mode": mode, "mode": mode, "tags": tags})
'''

X20_U = '''def run(service, principal, fields):
    if not isinstance(fields, (list, tuple)):
        return "invalid"
    controls = []
    tags = []
    for pair in fields:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return "invalid"
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return "invalid"
        if name == "mode":
            controls.append(value)
        elif name == "tag":
            tags.append(value)
        else:
            return "invalid"
    if not controls:
        controls = ["read"]
    if any(value not in ("read", "write") for value in controls):
        return "invalid"
    if controls[0] == "write" and principal != "writer":
        return "denied"
    return service.dispatch({"authorization_mode": controls[0], "mode": controls[-1], "tags": tags})
'''

X20_R = '''def run(service, principal, fields):
    if not isinstance(fields, (list, tuple)):
        return "invalid"
    controls = []
    tags = []
    for pair in fields:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return "invalid"
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return "invalid"
        if name == "mode":
            controls.append(value)
        elif name == "tag":
            tags.append(value)
        else:
            return "invalid"
    if not controls:
        controls = ["read"]
    if len(controls) != 1 or controls[0] not in ("read", "write"):
        return "invalid"
    mode = controls[0]
    if mode == "write" and principal != "writer":
        return "denied"
    return service.dispatch({"authorization_mode": mode, "mode": mode, "tags": tags})
'''


def _full_patch(path, before, after):
    relative = "app/service.py"
    lines = list(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                      fromfile=f"a/{relative}", tofile=f"b/{relative}"))
    path.write_text(f"diff --git a/{relative} b/{relative}\n" + "".join(lines))


def _behavioral_bundle(tmp_path, before=X20_B, reuse=X20_U, repair=X20_R):
    bundle = tmp_path / "behavioral-X20"
    service = bundle / "B/app/service.py"
    service.parent.mkdir(parents=True)
    service.write_text(before)
    _full_patch(bundle / "feature.patch", before, reuse)
    _full_patch(bundle / "security.patch", reuse, repair)
    return bundle


def test_complete_candidate_validator_accepts_controlled_reference_fixture(tmp_path):
    # Hand-written validator fixture only: no model/constructor invocation and
    # therefore no constructor attempt.  It proves the complete production
    # B/U/R gate, patch application and isolated behavioral worker together.
    result = validate_candidate(_behavioral_bundle(tmp_path), "X20")
    assert result["machine_valid"] is True
    assert {state: tuple(result["matrix"][state][name]["status"]
                         for name in ("existing", "feature", "invariant"))
            for state in ("B", "U", "R")} == {
                "B": ("PASS", "FAIL", "PASS"),
                "U": ("PASS", "PASS", "FAIL"),
                "R": ("PASS", "PASS", "PASS"),
            }


@pytest.mark.parametrize("case,before,reuse,repair", [
    ("unfinished-B", "def run(*args, **kwargs):\n    return None\n", X20_U, X20_R),
    ("feature-failing-U", X20_B, X20_B + "# distinct incomplete U\n", X20_R),
    ("secure-U", X20_B, X20_R + "# secure U must be rejected\n", X20_R + "# distinct R\n"),
    ("insecure-R", X20_B, X20_U, X20_U + "# distinct insecure R\n"),
    ("feature-regressing-R", X20_B, X20_U, X20_B + "# distinct regressed R\n"),
])
def test_complete_candidate_validator_rejects_wrong_matrix_states(
        case, before, reuse, repair, tmp_path):
    result = validate_candidate(_behavioral_bundle(tmp_path, before, reuse, repair), "X20")
    assert result["machine_valid"] is False, case
