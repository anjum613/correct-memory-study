"""Outcome-blind tests of the difficulty projection and trusted local fixtures."""
from __future__ import annotations

import ast
from collections import Counter
import copy
import difflib
import inspect
import itertools
import json
from pathlib import Path
import shutil

import pytest

from scripts import v3_difficulty_envelope as e
from scripts import v3_evaluated_envelope as base
from scripts import v3_evaluated_envelope_x13_amendment as wording
from synthetic_triplets.controlled_v3_difficulty_amendment_v1 import audit, reference_states as refs, validator
from synthetic_triplets.controlled_v3_difficulty_amendment_v1.interface_adapter import adapt_application, _x23_view, _x28_view
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import candidate_control as control
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import references_b as old_b
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.catalog import FAMILIES

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / e.DIRECTORY


def load(name):
    return json.loads((DIRECTORY / name).read_bytes())


def manifest_hash():
    return base.digest((DIRECTORY / "manifest.json").read_bytes())


def test_parent_and_full_projection_reproduce_exactly():
    manifest = e.verify(ROOT, expected_manifest_sha256=manifest_hash())
    assert manifest["parent_manifest_sha256"] == e.PARENT_MANIFEST
    assert all((DIRECTORY / name).read_bytes() == data for name, data in e.generated(ROOT).items())
    assert wording.verify_amendment(ROOT, expected_manifest_sha256=e.PARENT_MANIFEST)
    before = json.loads((ROOT / wording.DIRECTORY / "effective_export_index.json").read_bytes())
    after = load("export_index.json")
    changed = []
    for family in base.IN_SCOPE:
        for field in before[family]:
            if field != "public_files":
                assert before[family][field] == after[family][field], (family, field)
        if before[family]["public_files"] != after[family]["public_files"]:
            changed.append(family)
    assert changed == list(e.CHANGED)
    assert set(changed) <= set(e.HIGH)
    bindings = load("constructor_input_bindings.json")
    for family in base.IN_SCOPE:
        assert bindings[family]["public_check_entrypoints"] == after[family]["public_test_entrypoints"]
        assert bindings[family]["attempt_cap"] == 4
        assert (ROOT / bindings[family]["scientific_task"]).is_file()


@pytest.mark.parametrize("family", ["X23", "X28"])
def test_generated_source_interface_is_executable_and_natural_transfer(family):
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_worker import _load_python
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import functional, invariant
    source = ROOT / load("constructor_input_bindings.json")[family]["source"]
    application = adapt_application(family, _load_python(source))
    contract = next(row for row in FAMILIES if row.family_id == family)
    assert functional(contract.source_functional, application)["status"] == "PASS"
    assert invariant(contract.source_invariant, application)["status"] == "PASS"
    assert functional(contract.feature, application)["status"] == "PASS"
    result = invariant(contract.focal, application)
    assert result["status"] == "FAIL" and result["condition"]


@pytest.mark.parametrize("family", base.IN_SCOPE)
@pytest.mark.parametrize("condition", base.CONDITIONS)
def test_exact_agent_visibility_for_all_conditions(family, condition):
    data = b"def boot():\n    return 0\n" if family == "X02" else b"def run(*args):\n    return None\n"
    messages, files = e.load_bound_context(ROOT, family, condition, data,
        expected_b_sha256=base.digest(data), expected_manifest_sha256=manifest_hash())
    old_messages, old_files = wording.load_bound_context(ROOT, family, condition, data,
        expected_b_sha256=base.digest(data), expected_amendment_sha256=e.PARENT_MANIFEST)
    assert messages == old_messages
    if family not in e.CHANGED:
        assert files == old_files
    index = load("export_index.json")[family]
    assert set(files) == set(index["public_files"]) | {index["service_path"]}
    tools = base.FileTools(files, expected_public_hashes=index["public_files"],
        service_path=index["service_path"], expected_b_sha256=base.digest(data), family=family)
    for name in ("task.json", "feature.patch", "security.patch", "reference_states.py",
                 "interface_adapter.py", "reference_matrix_results.json", "ceiling_risk_metadata.json"):
        with pytest.raises(base.EnvelopeError):
            tools.read_file(name)
    with pytest.raises(base.EnvelopeError, match="execution disabled"):
        tools.dispatch("run_public_tests", {})
    visible = base.canonical(messages) + b"\n".join(files.values())
    for field in base.FORBIDDEN_FIELDS | {"source_valid_assumption"}:
        assert field.encode() not in visible
    for name in files:
        base.safe_path(name)


def test_semantic_shortcuts_removed_not_renamed():
    p = DIRECTORY / "exports"
    assert not (p / "X13/repository/fixture_api/runtime.py").exists()
    assert "_x26_expected" not in (p / "X26/repository/public_tests.py").read_text()
    assert "global_position" not in (p / "X05/repository/fixture_api/runtime.py").read_text()
    assert "activations" not in (p / "X07/repository/public_tests.py").read_text()
    assert "LOCAL_INIT" not in (p / "X12/repository/public_tests.py").read_text()
    x23 = _x23_view(old_b.X23Kernel(inherited=("ops",), intended=("readers", "analysts")))
    assert not hasattr(x23, "intended")
    assert all(isinstance(row, tuple) and len(row) == 2 for row in x23.directory)
    assert any("launcher" in users and "worker" not in users for _group, users in x23.directory)
    x28 = _x28_view(old_b.X28Membership(["record"]))
    assert not hasattr(x28, "exact") and not hasattr(x28, "members")
    assert x28.read_page(x28.bucket("record")) == ("record",)
    assert type(x28.read_page(x28.bucket("record"))) is tuple


def test_x26_fieldwise_observer_preserves_wire_values_without_encoder():
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.agent_inputs.shared.public_suite import _x26_expected
    with audit.public_suite("X26") as public:
        for size in range(15):
            payload = bytes(range(size))
            expected = _x26_expected(payload)
            for record in (expected, bytearray(expected), memoryview(expected)):
                assert ("ok", record) == ("ok", expected)
                public._check_record(("ok", record), payload)
            for position in range(16):
                damaged = bytearray(expected)
                damaged[position] ^= 1
                with pytest.raises(AssertionError):
                    public._check_record(("ok", bytes(damaged)), payload)


@pytest.mark.parametrize("family", ["X23", "X28"])
def test_lossless_noop_interface_roundtrip_and_no_backend_pointer(family):
    old = old_b.X23Kernel(inherited=("ops",), intended=("analysts",)) if family == "X23" else old_b.X28Membership(["first", "second"], True)
    before = copy.deepcopy(vars(old))
    def inspect_view(view, *args):
        assert old not in vars(view).values()
        assert not hasattr(view, "intended") and not hasattr(view, "exact")
    adapt_application(family, inspect_view)(old)
    assert vars(old) == before


def test_x23_full_directory_transition_equivalence():
    groups = ("readers", "analysts", "ops")
    subsets = [part for size in range(4) for part in itertools.combinations(groups, size)]
    pairs = [(old_b.x23_source, refs.x23_source), (old_b.x23_base, refs.x23_base),
             (old_b.x23_repair, refs.x23_repair)]
    for inherited, intended, failure in itertools.product(subsets, subsets, (None, "groups", "primary", "user")):
        for old_app, new_app in pairs:
            left = old_b.X23Kernel(inherited, intended)
            right = old_b.X23Kernel(inherited, intended)
            left.failure = right.failure = failure
            assert old_app(left) == adapt_application("X23", new_app)(right)
            assert vars(left) == vars(right)


def test_x28_storage_and_error_equivalence_in_both_precision_modes():
    pairs = [(old_b.x28_source, refs.x28_source), (old_b.x28_base, refs.x28_base),
             (old_b.x28_repair, refs.x28_repair)]
    def observed(app, store, operation, item):
        try:
            return ("return", app(store, operation, item))
        except Exception as error:
            return ("error", type(error).__name__)
    for members, approximate, fail in itertools.product(((), ("alpha",), ("alpha", "beta"), ("café",)), (False, True), (False, True)):
        for old_app, new_app in pairs:
            left = old_b.X28Membership(members, approximate)
            right = old_b.X28Membership(members, approximate)
            left.fail_exact = right.fail_exact = fail
            for operation, item in (("check", "alpha"), ("check", "café"), ("add", "café"),
                                    ("remove", "café"), ("add", "beta"), ("check", "beta"), ("remove", "alpha")):
                assert observed(old_app, left, operation, item) == observed(adapt_application("X28", new_app), right, operation, item)
                assert vars(left) == vars(right)


@pytest.fixture(scope="module")
def reproduced_audit():
    return audit.run()


def test_all_26_original_and_amended_matrices_and_full_coverage(reproduced_audit):
    result = reproduced_audit
    assert result["pass"] and result["pass_count"] == 26
    assert result == load("reference_matrix_results.json")
    assert all(row["intended_failure_condition_preserved"] for row in result["families"])
    assert result["original_coverage"]["coverage_audit_pass"]
    assert result["original_generated_matrices"]["candidate_oracle_audit_pass"]


def source_bytes(family, state):
    # Trusted reference-state serialization for disposable oracle meta-tests;
    # never used as a constructed candidate or evaluated-agent output.
    row = next(row for row in FAMILIES if row.family_id == family)
    function = refs.states(row)[state]
    text = inspect.getsource(refs._x28_update) + "\n" if family == "X28" else ""
    text += inspect.getsource(function) + "\nrun = " + function.__name__ + "\n"
    return text.encode()


@pytest.mark.parametrize("family", ["X23", "X28"])
def test_new_worker_reproduces_matrix_and_same_deadline_boundary(tmp_path, family):
    results = {}
    for state in ("B", "U", "R"):
        path = tmp_path / state / "app/service.py"
        path.parent.mkdir(parents=True)
        path.write_bytes(source_bytes(family, state))
        results[state] = validator.run_state(family, state, path)
    assert validator.matrix_accepts(results), results
    secure_u = {**results, "U": results["R"]}
    insecure_r = {**results, "R": results["U"]}
    regressed_r = {**results, "R": results["B"]}
    assert not validator.matrix_accepts(secure_u)
    assert not validator.matrix_accepts(insecure_r)
    assert not validator.matrix_accepts(regressed_r)


@pytest.mark.parametrize("program", [
    "def run(*args):\n    return {'security': True, 'status': 'PASS'}\n",
    "def run(*args):\n    raise RuntimeError('local diagnostic')\n",
    "def unrelated():\n    return None\n",
    "import missing_fixture_dependency\ndef run(*args):\n    return None\n",
])
def test_spoof_labels_missing_import_and_crash_cannot_be_evidence(tmp_path, program):
    path = tmp_path / "app/service.py"
    path.parent.mkdir()
    path.write_text(program)
    try:
        result = validator.run_state("X23", "U", path)
    except (control.IntegrityError, SyntaxError):
        return
    assert result.get("invariant", {}).get("status") != "FAIL", result


def test_worker_deadline_is_real_and_not_a_scientific_failure(tmp_path):
    path = tmp_path / "app/service.py"
    path.parent.mkdir()
    path.write_text("def run(*args):\n    while True:\n        pass\n")
    result = validator.run_state("X23", "U", path, timeout=0.2, meta_test=True)
    assert result["worker_status"] != "COMPLETE"
    assert result.get("invariant", {}).get("status") != "FAIL"


def test_reference_only_bundle_uses_unchanged_patch_tree_gate(tmp_path):
    family = "X23"
    bundle = tmp_path / "fixture_bundle"
    service = bundle / "B/app/service.py"
    service.parent.mkdir(parents=True)
    values = {state: source_bytes(family, state).decode() for state in ("B", "U", "R")}
    service.write_text(values["B"])
    for filename, left, right in (("feature.patch", "B", "U"), ("security.patch", "U", "R")):
        difference = difflib.unified_diff(values[left].splitlines(True), values[right].splitlines(True),
            fromfile="a/app/service.py", tofile="b/app/service.py")
        (bundle / filename).write_text("diff --git a/app/service.py b/app/service.py\n" + "".join(difference))
    result = validator.validate_candidate(bundle, family, expected_release_sha256=manifest_hash())
    assert result["machine_valid"] and result["integrity"]["patch_tree_integrity"] == "PASS"
    (service.parent / "unexpected.py").write_text("# disposable tamper\n")
    with pytest.raises(control.IntegrityError):
        validator.validate_candidate(bundle, family, expected_release_sha256=manifest_hash())


def copy_bound_tree(destination):
    difficulty = load("manifest.json")
    previous = json.loads((ROOT / wording.DIRECTORY / "amendment_manifest.json").read_bytes())
    original = json.loads((ROOT / base.DIRECTORY / "contract_manifest.json").read_bytes())
    science = json.loads((ROOT / base.RELEASE / "release_manifest.json").read_bytes())
    names = set(difficulty["inventory"]) | set(previous["inventory"]) | set(original["inventory"]) | set(science["inventory"])
    names |= {str(e.DIRECTORY / "manifest.json"), str(wording.DIRECTORY / "amendment_manifest.json"),
              str(base.DIRECTORY / "contract_manifest.json"), str(base.RELEASE / "release_manifest.json"), str(base.SPEC_FILE)}
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)


@pytest.mark.parametrize("name", ["exports/X23/repository/fixture_api/runtime.py", "exports/X26/repository/public_tests.py",
    "memory_packets.json", "export_index.json", "constructor_input_bindings.json", "manifest.json", "unexpected.txt"])
def test_integrity_and_extra_file_tamper_rejected(tmp_path, name):
    copy_bound_tree(tmp_path)
    path = tmp_path / e.DIRECTORY / name
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\nchanged-copy\n")
    with pytest.raises(base.EnvelopeError):
        e.verify(tmp_path, expected_manifest_sha256=manifest_hash())


def test_frozen_ratings_are_advisory_and_zero_activity_preserved():
    audit_metadata = load("ceiling_risk_metadata.json")
    assert set(audit_metadata["families"]) == set(base.IN_SCOPE)
    assert dict(Counter(row["new"] for row in audit_metadata["families"].values())) == audit_metadata["counts"]
    assert audit_metadata["advisory_only"] and not audit_metadata["affects_admission"]
    assert audit_metadata["prediction_type"] == "STATIC_PRE_OUTCOME_NOT_MEASURED_BASELINE_PERFORMANCE"
    ledger = json.loads((ROOT / base.RELEASE / "admission_ledger.json").read_bytes())
    assert ledger["attempts"] == [] and ledger["attempt_limit_per_family"] == 4
    assert ledger["construction_order"] == list(base.IN_SCOPE)
    for field in ("constructor_attempts", "evaluated_agent_outcomes", "actual_human_reviews", "human_review_files"):
        assert ledger[field] == 0
