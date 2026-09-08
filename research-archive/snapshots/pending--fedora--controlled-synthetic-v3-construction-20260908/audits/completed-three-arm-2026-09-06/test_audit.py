"""Tests for derived audit logic only, not evaluated programs or witnesses."""

import copy

import pytest

from audit_analysis import ARMS, HERE, exact_sign_flip, load, missing_bounds, ngrams, paired_units, quantile
from audit_extract import outcome
from render_casebook import validate_annotations


def test_quantile_and_sign_flip():
    assert quantile([0, 10], .25) == 2.5
    assert exact_sign_flip([0, 0, 0]) == 1
    assert exact_sign_flip([1, 1]) == .5
    assert ngrams("One two, three four five six seven EIGHT.") == {("one", "two", "three", "four", "five", "six", "seven", "eight")}


def test_outcome_is_joint_not_security_alone():
    r = dict(technical_valid=True, evaluation=dict(functionality_pass=False, focal_security_pass=True))
    assert outcome(r) == "INCOMPLETE_SECURITY_PASS"
    r["technical_valid"] = False
    assert outcome(r) == "INVALID"


def test_seed_pairing_and_missingness_are_not_independent_trials():
    rows = load(HERE / "runs.json")
    original = copy.deepcopy(rows)
    units = paired_units(rows, "C", "N")
    assert len(units) == 38
    assert sum(u["delta"] for u in units) / 38 == pytest.approx(-.06578947368421052)
    assert not any(u["model"] == "Dev" and u["family"] == "X02" for u in units)
    assert any(u["model"] == "Q30" and u["family"] == "X02" for u in units)
    assert rows == original


def test_recorded_scores_and_all_frozen_conditions():
    rows = load(HERE / "runs.json")
    assert len(rows) == len({r["key"] for r in rows}) == 312
    for model, expected in zip(ARMS, [(104,65,46,19), (102,90,58,32), (102,95,52,43)]):
        rr = [r for r in rows if r["model"] == model and r["valid"]]
        assert (len(rr), sum(r["fun"] for r in rr), sum(r["unsafe"] for r in rr), sum(r["safe"] for r in rr)) == expected
    assert all(all(v for k,v in r.items() if k != "key") for r in load(HERE/"integrity.json"))


def test_missing_bounds_leave_original_invalids_unscored():
    rows = [r for r in load(HERE/"runs.json") if r["model"] == "Dev"]
    bounds = missing_bounds(rows, "C", "N")
    assert bounds["lower_pp"] == pytest.approx(-200/26)
    assert bounds["upper_pp"] == pytest.approx(-100/26)
    assert all(r["unsafe"] is None for r in rows if not r["valid"])


def test_all_reported_transcript_quotes_are_exact():
    _, _, cases = validate_annotations()
    assert len(cases) == 17
