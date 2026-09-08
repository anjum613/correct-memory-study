"""Additive X13 wording/information-flow tests; no construction or agent runs."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil

import pytest

from scripts import v3_evaluated_envelope as base
from scripts import v3_evaluated_envelope_x13_amendment as a
from scripts.freeze_v3_evaluated_envelope_x13_amendment import freeze

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / a.DIRECTORY


def load(name):
    return json.loads((DIRECTORY / name).read_bytes())


def manifest_hash():
    # Test harness binding only. Production requires a separately trusted hash.
    return base.digest((DIRECTORY / "amendment_manifest.json").read_bytes())


def dummy_service(family):
    # Generic file-boundary bytes: never submitted to any constructor or oracle.
    return b"def boot():\n    return 0\n" if family == "X02" else b"def run(*args):\n    return None\n"


def context(family="X13", condition="NO_MEMORY", root=ROOT):
    data = dummy_service(family)
    return a.load_bound_context(root, family, condition, data,
        expected_b_sha256=base.digest(data), expected_amendment_sha256=manifest_hash())


def test_exact_overlay_and_five_binding_changes_only():
    base.verify_contract(ROOT, expected_manifest_sha256=a.BASE_MANIFEST_SHA256)
    assert a.verify_amendment(ROOT, expected_manifest_sha256=manifest_hash())["amendment_id"] == a.AMENDMENT_ID
    original = (ROOT / base.DIRECTORY / a.TASK_PATH).read_bytes()
    expected = original.replace(a.OLD_PHRASE.encode(), a.NEW_PHRASE.encode(), 1)
    assert (DIRECTORY / a.TASK_PATH).read_bytes() == expected
    for name, value in a.generated_overlay(ROOT).items():
        assert (DIRECTORY / name).read_bytes() == value
    original_index = json.loads((ROOT / base.DIRECTORY / "export_index.json").read_bytes())
    effective = load("effective_export_index.json")
    changes = []
    for family in base.IN_SCOPE:
        for key, value in original_index[family].items():
            if isinstance(value, dict):
                assert set(value) == set(effective[family][key])
                changes.extend(f"{family}.{key}.{sub}" for sub in value if value[sub] != effective[family][key][sub])
            elif value != effective[family][key]:
                changes.append(f"{family}.{key}")
    assert sorted(changes) == sorted(a.expected_binding_changes())


@pytest.mark.parametrize("family", base.IN_SCOPE)
@pytest.mark.parametrize("condition", base.CONDITIONS)
def test_all_104_effective_envelopes_only_x13_phrase_differs(family, condition):
    data = dummy_service(family)
    old_messages, old_files = base.load_bound_context(ROOT, family, condition, data,
        expected_b_sha256=base.digest(data), expected_contract_sha256=a.BASE_MANIFEST_SHA256)
    messages, files = context(family, condition)
    assert files == old_files
    assert messages[0] == old_messages[0]
    expected = old_messages[1]["content"]
    if family == "X13":
        assert expected.count(a.OLD_PHRASE) == 1
        expected = expected.replace(a.OLD_PHRASE, a.NEW_PHRASE, 1)
    assert messages[1] == {"role": "user", "content": expected}
    index = load("effective_export_index.json")[family]
    assert set(files) == set(index["public_files"]) | {index["service_path"]}
    assert base.digest(base.canonical(messages)) == index["messages_sha256"][condition]
    task_dir = DIRECTORY if family == "X13" else ROOT / base.DIRECTORY
    task = (task_dir / f"exports/{family}/target_request.txt").read_text()
    packets = json.loads((ROOT / base.DIRECTORY / "memory_packets.json").read_bytes())
    assert messages == base.render_messages(family, condition, task, packets)
    if condition == "NO_MEMORY":
        assert messages[1]["content"] == task
        assert "[BEGIN_MEMORY_CONTEXT]" not in expected
    else:
        packet = expected[len(task) + 1:]
        assert len(packet.encode()) == base.MEMORY_BYTES
        assert packet.count(base.BOUNDARY) == int(condition == base.CONDITIONS[3])
    visible = base.canonical(messages) + b"\n".join(files.values())
    for word in base.FORBIDDEN_FIELDS | {"source_valid_assumption", "STATIC_PRE_OUTCOME_PREDICTIONS_NOT_MEASURED_BASELINE_PERFORMANCE"}:
        assert word.encode() not in visible
    for name in files:
        base.safe_path(name)
        assert "ceiling_risk" not in name and "amendment" not in name


@pytest.mark.parametrize("mutation", [b"", b"\n", b"prefix", b"define rounding and range policy prospectively."])
def test_renderer_rejects_unbound_or_caller_modified_task(mutation):
    original = (ROOT / base.DIRECTORY / a.TASK_PATH).read_bytes()
    changed = mutation if not mutation else original + mutation
    with pytest.raises(base.EnvelopeError):
        a.corrected_x13_task(changed)


@pytest.mark.parametrize("family", ["X19", "X25", "X29"])
def test_no_new_or_excluded_family_can_be_exported(family):
    with pytest.raises(base.EnvelopeError):
        context(family)


def test_advisory_metadata_is_complete_not_an_admission_rule():
    audit = load("ceiling_risk_metadata.json")
    assert set(audit["families"]) == set(base.IN_SCOPE)
    assert dict(Counter(row["rating"] for row in audit["families"].values())) == audit["counts"]
    assert audit["prediction_type"] == "STATIC_PRE_OUTCOME_PREDICTIONS_NOT_MEASURED_BASELINE_PERFORMANCE"
    assert audit["advisory_only"] is True
    for field in ("affects_admission", "affects_order_or_attempt_limits", "authorizes_exclusion_or_redesign", "visible_to_evaluated_agent"):
        assert audit[field] is False
    assert audit["cohort_summary"]["families_excluded_or_redesigned_by_this_audit"] == []
    ledger = json.loads((ROOT / base.RELEASE / "admission_ledger.json").read_bytes())
    assert ledger["attempt_limit_per_family"] == 4
    assert ledger["construction_order"] == list(base.IN_SCOPE)
    assert ledger["attempts"] == []
    for field in ("constructor_attempts", "evaluated_agent_outcomes", "actual_human_reviews", "human_review_files"):
        assert ledger[field] == 0


def broker():
    _messages, files = context()
    index = load("effective_export_index.json")["X13"]
    return base.FileTools(files, expected_public_hashes=index["public_files"],
        service_path=index["service_path"], expected_b_sha256=base.digest(dummy_service("X13")), family="X13")


@pytest.mark.parametrize("path", ["ceiling_risk_metadata.json", "effective_export_index.json", "amendment_manifest.json", "task.json", "feature.patch", "security.patch", "researcher_tests/X13/sealed_tests.py", "references/R.py", "references/U.py", "../README.md", "constructor_traces.json", "validator_decisions.json"])
def test_amended_tool_map_cannot_read_researcher_or_repair_artifacts(path):
    with pytest.raises(base.EnvelopeError):
        broker().dispatch("read_file", {"path": path})


def test_no_tool_execution_or_public_file_edit_is_enabled():
    tools = broker()
    with pytest.raises(base.EnvelopeError, match="execution disabled"):
        tools.dispatch("run_public_tests", {})
    with pytest.raises(base.EnvelopeError):
        tools.dispatch("edit_service", {"path": "public_tests.py", "old_sha256": "0" * 64, "replacement": ""})
    for operation in ("shell", "constructor", "evaluate", "human_review", "git"):
        with pytest.raises(base.EnvelopeError):
            tools.dispatch(operation, {})


def copy_bound_tree(destination):
    manifest = load("amendment_manifest.json")
    parent = json.loads((ROOT / base.DIRECTORY / "contract_manifest.json").read_bytes())
    science = json.loads((ROOT / base.RELEASE / "release_manifest.json").read_bytes())
    names = set(manifest["inventory"]) | set(parent["inventory"]) | set(science["inventory"])
    names |= {str(a.DIRECTORY / "amendment_manifest.json"), str(base.DIRECTORY / "contract_manifest.json"),
              str(base.RELEASE / "release_manifest.json"), str(base.SPEC_FILE)}
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)


@pytest.mark.parametrize("mutation", ["task", "index", "rating", "old-contract", "old-public", "science", "extra-file", "manifest", "symlink"])
def test_overlay_and_transitive_tampering_rejected(tmp_path, mutation):
    copy_bound_tree(tmp_path)
    a.verify_amendment(tmp_path, expected_manifest_sha256=manifest_hash())
    paths = {
        "task": a.DIRECTORY / a.TASK_PATH,
        "index": a.DIRECTORY / "effective_export_index.json",
        "rating": a.DIRECTORY / "ceiling_risk_metadata.json",
        "old-contract": base.DIRECTORY / "contract.json",
        "old-public": base.DIRECTORY / "exports/X13/repository/public_tests.py",
        "science": base.SPEC_FILE,
        "extra-file": a.DIRECTORY / "unexpected.txt",
        "manifest": a.DIRECTORY / "amendment_manifest.json",
        "symlink": a.DIRECTORY / a.TASK_PATH,
    }
    target = tmp_path / paths[mutation]
    if mutation == "symlink":
        target.unlink()
        target.symlink_to(ROOT / a.DIRECTORY / a.TASK_PATH)
    else:
        target.write_bytes((target.read_bytes() if target.exists() else b"") + b"\nchanged-copy-only\n")
    with pytest.raises(base.EnvelopeError):
        a.verify_amendment(tmp_path, expected_manifest_sha256=manifest_hash())


def test_caller_cannot_authorize_a_rewritten_manifest(tmp_path):
    copy_bound_tree(tmp_path)
    manifest_path = tmp_path / a.DIRECTORY / "amendment_manifest.json"
    target = tmp_path / a.DIRECTORY / a.TASK_PATH
    target.write_bytes(target.read_bytes() + b"unbound instructions\n")
    manifest = json.loads(manifest_path.read_bytes())
    manifest["inventory"][str(a.DIRECTORY / a.TASK_PATH)] = base.digest(target.read_bytes())
    manifest["content_sha256"] = base.digest(base.canonical(manifest["inventory"]))
    manifest_path.write_bytes(base.canonical(manifest))
    with pytest.raises(base.EnvelopeError, match="trusted external binding"):
        a.verify_amendment(tmp_path, expected_manifest_sha256=manifest_hash())


def test_generation_refuses_committed_receipt(tmp_path):
    directory = tmp_path / a.DIRECTORY
    directory.mkdir(parents=True)
    (directory / "commit_receipt.json").write_text("{}\n")
    with pytest.raises(FileExistsError):
        freeze(tmp_path)
