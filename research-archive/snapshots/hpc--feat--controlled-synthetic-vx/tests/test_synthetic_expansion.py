"""Admission-state regression tests; fixture candidates are inert text, not code."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts.verify_synthetic_expansion import (
    EXPANSION, GATES, INPUT_ROLES, PRE_GATES, assess_ledger, inventory_digest,
    main, read_object, sha256, utc, verify, verify_specs,
)


BASE = datetime(2026, 9, 5, tzinfo=timezone.utc)


def stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": name, "sha256": sha256(path)}


class Study:
    def __init__(self, root):
        self.root = root
        self.protocol = read_object(EXPANSION / "protocol.json")
        self.freeze = "test-only-specification-anchor"
        self.ledger = {
            "schema_version": "controlled-synthetic-expansion-ledger/1",
            "freeze_sha256": self.freeze,
            "evaluated_agent_outcomes_observed": False,
            "agent_experiment_frozen": False,
            "construction_release": None,
            "families": [],
        }
        inputs = {role: put(root, f"inputs/{role}.json", {"fixture": "inert", "role": role})
                  for role in INPUT_ROLES}
        inventory = {ref["path"]: ref["sha256"] for ref in inputs.values()}
        packages = []
        for family in self.protocol["new_family_order"]:
            audit = put(root, f"audits/{family}.json", {
                "family_id": family, "reviewer_id": "fixture-design-owner",
                "reviewer_type": "design_owner", "outcome_blind": True,
                "submitted_at_utc": stamp(1), "attestation": "TEST FIXTURE ONLY",
                "gates": {key: {"passed": True, "evidence": "fixture audit"} for key in PRE_GATES},
            })
            inventory[audit["path"]] = audit["sha256"]
            packages.append({"family_id": family, "audit_path": audit["path"],
                             "inputs": {role: [inputs[role]["path"]] for role in INPUT_ROLES}})
        self.release = {
            "schema_version": "construction-input-release/1", "freeze_sha256": self.freeze,
            "frozen_at_utc": stamp(2), "no_evaluated_outcomes": True,
            "owner_attestation": "TEST FIXTURE ONLY",
            "constructor": {"model": "fixture", "version": "inert-1", **self.protocol["constructor_controls"]},
            "inventory": inventory, "packages": packages,
        }
        self.bind_release()

    def bind_release(self):
        self.ledger["construction_release"] = put(self.root, "release.json", self.release)

    def assess(self):
        return assess_ledger(self.root, self.protocol, self.ledger, self.freeze, utc(stamp(0)))

    def add(self, *, valid=True, primary=(True, True), third=None, attempts=1):
        index = len(self.ledger["families"])
        family = self.protocol["new_family_order"][index]
        before = self.assess()["retained"]
        row = {"family_id": family, "attempts": [], "reviews": []}
        offset = 10 + index * 100
        digest = None
        for number in range(1, attempts + 1):
            inventory = {}
            for name in ("B/app/service.py", "feature.patch", "security.patch"):
                ref = put(self.root, f"evidence/{family}/{number}/candidate/{name}",
                          {"fixture": family, "attempt": number, "file": name})
                inventory[ref["path"]] = ref["sha256"]
            digest = inventory_digest(inventory)
            passed = valid and number == attempts
            checks = {key: passed for key in self.protocol["mandatory_machine_checks"]}
            report = put(self.root, f"evidence/{family}/{number}/machine.json", {
                "family_id": family, "attempt_number": number, "candidate_sha256": digest,
                "input_release_sha256": self.ledger["construction_release"]["sha256"],
                "checks": checks, "machine_valid": passed,
            })
            trace = put(self.root, f"evidence/{family}/{number}/trace.json", {"test_fixture": True})
            row["attempts"].append({
                "number": number, "started_at_utc": stamp(offset + number * 2),
                "completed_at_utc": stamp(offset + number * 2 + 1),
                "input_release_sha256": self.ledger["construction_release"]["sha256"],
                "constructor": deepcopy(self.release["constructor"]), "artifacts": inventory,
                "trace": trace, "machine_report": report,
            })
        decisions = list(primary) + ([third] if third is not None else []) if valid else []
        for i, decision in enumerate(decisions):
            role = ("primary_1", "primary_2", "adjudicator")[i]
            flags = {key: decision for key in GATES} if isinstance(decision, bool) else decision
            record = {
                "reviewer_id": f"fixture-human-{i}", "role": role, "reviewer_type": "human",
                "candidate_sha256": digest, "input_release_sha256": self.ledger["construction_release"]["sha256"],
                "submitted_at_utc": stamp(offset + 30 + i), "outcome_blind": True,
                "other_primary_review_seen_before_submission": False,
                "compared_retained_family_ids": list(before),
                "gates": {key: {"passed": flags[key], "evidence": "TEST FIXTURE ONLY"} for key in GATES},
                "attestation": "TEST FIXTURE ONLY", "signature_form": "NON_CRYPTOGRAPHIC_HUMAN_ATTESTATION",
                "disagreement_resolution": {},
            }
            if i == 2:
                first = read_object(self.root / row["reviews"][0]["path"])["gates"]
                second = read_object(self.root / row["reviews"][1]["path"])["gates"]
                record["disagreement_resolution"] = {key: "fixture resolution" for key in GATES
                                                     if first[key]["passed"] != second[key]["passed"]}
            row["reviews"].append(put(self.root, f"reviews/{family}/{role}.json", record))
        self.ledger["families"].append(row)
        return row

    def edit_review(self, row, index, edit):
        ref = row["reviews"][index]
        record = read_object(self.root / ref["path"])
        edit(record)
        row["reviews"][index] = put(self.root, ref["path"], record)


@pytest.fixture
def study(tmp_path):
    return Study(tmp_path)


def test_frozen_release_preserves_six_and_blocks_experiment():
    result = verify()
    assert result["specification_count"] == 28
    assert result["retained"] == ["F01", "F02", "F04", "F08", "F17", "F20"]
    assert result["final_count"] == 6
    assert result["machine_valid_count"] == result["attempt_count"] == 0
    assert not result["experiment_freeze_eligible"]
    assert not result["evaluated_agent_runs_authorized"]
    assert main(["--check", "--require-experiment-ready"]) == 2


def test_all_specs_have_one_change_and_complete_contract():
    protocol = read_object(EXPANSION / "protocol.json")
    specs = read_object(EXPANSION / "family_specs.json")["specifications"]
    verify_specs(protocol, specs)
    specs[0]["trust_matrix"][1]["target"] = "a second changed trust dimension"
    with pytest.raises(ValueError, match="exactly one"):
        verify_specs(protocol, specs)


def test_no_attempts_before_fixed_release(study):
    study.add()
    study.ledger["construction_release"] = None
    with pytest.raises(ValueError, match="before fixed input release"):
        study.assess()


def test_all_28_packages_frozen_before_first_constructor(study):
    study.release["packages"].pop()
    study.bind_release()
    with pytest.raises(ValueError, match="all 28"):
        study.assess()


def test_sealed_evidence_cannot_be_in_public_inventory(study):
    package = study.release["packages"][0]
    package["inputs"]["public"] = package["inputs"]["sealed"]
    study.bind_release()
    with pytest.raises(ValueError, match="sealed evidence"):
        study.assess()


def test_constructor_controls_cannot_drift(study):
    row = study.add()
    row["attempts"][0]["constructor"]["version"] = "another-version"
    with pytest.raises(ValueError, match="model/control drift"):
        study.assess()


def test_retained_six_are_in_exact_duplicate_check(study):
    row = study.add()
    paths = row["attempts"][0]["artifacts"]
    base = Path(next(p for p in paths if p.endswith("feature.patch"))).parent
    digest = inventory_digest({Path(p).relative_to(base).as_posix(): value for p, value in paths.items()})
    with pytest.raises(ValueError, match="duplicate retained"):
        assess_ledger(study.root, study.protocol, study.ledger, study.freeze, utc(stamp(0)), (digest,))


def test_machine_valid_candidate_uses_both_primary_reviews(study):
    study.add(attempts=3)
    result = study.assess()
    assert result["additional_admitted"] == ["X01"]
    assert result["attempt_count"] == 3
    assert result["next_family"] == "X02"


def test_first_rejection_still_requires_second_human(study):
    study.add(primary=(False,))
    assert study.assess()["status"] == "HUMAN_REVIEW_PENDING"
    study.ledger["families"].append({"family_id": "X02", "attempts": [], "reviews": []})
    with pytest.raises(ValueError, match="before prior disposition"):
        study.assess()


@pytest.mark.parametrize("primary,third,expected", [
    ((True, False), None, "ADJUDICATION_PENDING"),
    ((False, True), True, "ADMITTED"),
    ((True, False), False, "ADJUDICATED_REJECTED"),
    ((False, False), None, "PRIMARY_REJECTED"),
])
def test_whole_contract_adjudication(study, primary, third, expected):
    study.add(primary=primary, third=third)
    assert study.assess()["dispositions"][0]["disposition"] == expected


def test_no_majority_assembly_from_incomplete_human_endorsements(study):
    first = {key: key != "6" for key in GATES}
    second = {key: key != "8" for key in GATES}
    study.add(primary=(first, second), third=True)
    assert study.assess()["attrition"]["ADJUDICATED_REJECTED"] == 1


def test_third_only_for_disagreement(study):
    study.add(third=True)
    with pytest.raises(ValueError, match="without disagreement"):
        study.assess()


def test_no_retry_after_first_machine_valid_even_if_human_rejects(study):
    row = study.add(primary=(False, False))
    row["attempts"].append(deepcopy(row["attempts"][0]))
    with pytest.raises(ValueError, match="after first machine-valid"):
        study.assess()


def test_four_failed_attempts_exhaust_specification(study):
    study.add(valid=False, attempts=4)
    assert study.assess()["attrition"]["MACHINE_EXHAUSTED"] == 1
    study.add()
    assert study.assess()["additional_admitted"] == ["X02"]


def test_cap_cannot_expand_for_failures(study):
    study.add(valid=False, attempts=5)
    with pytest.raises(ValueError, match="limit exceeded"):
        study.assess()


def test_strict_order_disallows_skipping(study):
    row = study.add()
    row["family_id"] = "X02"
    with pytest.raises(ValueError, match="skipped or reordered"):
        study.assess()


@pytest.mark.parametrize("field,value,message", [
    ("other_primary_review_seen_before_submission", True, "independently sealed"),
    ("reviewer_type", "AI", "AI or unidentified"),
    ("candidate_sha256", "different", "candidate binding"),
    ("input_release_sha256", "different", "input binding"),
    ("outcome_blind", False, "outcome blind"),
    ("compared_retained_family_ids", [], "duplicate comparison"),
    ("submitted_at_utc", stamp(0), "predates candidate"),
    ("attestation", "", "attestation"),
])
def test_human_evidence_requirements(study, field, value, message):
    row = study.add()
    study.edit_review(row, 0, lambda record: record.update({field: value}))
    with pytest.raises(ValueError, match=message):
        study.assess()


def test_same_human_cannot_fill_two_roles(study):
    row = study.add()
    study.edit_review(row, 1, lambda r: r.update(reviewer_id="fixture-human-0"))
    with pytest.raises(ValueError, match="distinct humans"):
        study.assess()


def test_adjudicator_must_address_every_disputed_gate(study):
    row = study.add(primary=(True, False), third=True)
    study.edit_review(row, 2, lambda r: r.update(disagreement_resolution={}))
    with pytest.raises(ValueError, match="every disputed gate"):
        study.assess()


def test_modified_candidate_evidence_is_rejected(study):
    row = study.add()
    path = next(iter(row["attempts"][0]["artifacts"]))
    (study.root / path).write_text("changed inert fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="digest changed"):
        study.assess()


def test_missing_full_condition_check_is_not_machine_valid(study):
    row = study.add()
    ref = row["attempts"][0]["machine_report"]
    report = read_object(study.root / ref["path"])
    report["checks"].pop("R_full_target_condition")
    row["attempts"][0]["machine_report"] = put(study.root, ref["path"], report)
    with pytest.raises(ValueError, match="incomplete machine"):
        study.assess()


def test_no_evaluated_outcomes_or_early_experiment_freeze(study):
    study.ledger["evaluated_agent_outcomes_observed"] = True
    with pytest.raises(ValueError, match="outcome-blind"):
        study.assess()
    study.ledger["evaluated_agent_outcomes_observed"] = False
    study.ledger["agent_experiment_frozen"] = True
    with pytest.raises(ValueError, match="cannot freeze"):
        study.assess()


def test_pre_generation_failure_is_separately_retired(study):
    package = study.release["packages"][0]
    audit = read_object(study.root / package["audit_path"])
    audit["gates"]["G08"]["passed"] = False
    ref = put(study.root, package["audit_path"], audit)
    study.release["inventory"][ref["path"]] = ref["sha256"]
    study.bind_release()
    study.ledger["families"].append({"family_id": "X01", "attempts": [], "reviews": []})
    assert study.assess()["attrition"]["SPEC_AUDIT_REJECTED"] == 1
    study.add()
    assert study.assess()["additional_admitted"] == ["X02"]


def test_immediate_stop_at_14_additions_and_no_automatic_agent_runs(study):
    study.add(primary=(False, False))
    for _ in range(14):
        study.add()
    result = study.assess()
    assert result["final_count"] == 20
    assert result["additional_admitted"] == [f"X{i:02d}" for i in range(2, 16)]
    assert result["experiment_freeze_eligible"]
    assert not result["evaluated_agent_runs_authorized"]
    assert result["unused_after_stop"] == [f"X{i:02d}" for i in range(16, 29)]
    study.ledger["families"].append({"family_id": "X16", "attempts": [], "reviews": []})
    with pytest.raises(ValueError, match="after immediate cohort stop"):
        study.assess()


def test_exhausted_pool_reports_shortfall_without_relaxing_gates(study):
    for _ in range(28):
        study.add(primary=(False, False))
    result = study.assess()
    assert result["status"] == "COHORT_INCOMPLETE_POOL_EXHAUSTED"
    assert result["final_count"] == 6
    assert not result["experiment_freeze_eligible"]
    assert result["next_family"] is None
