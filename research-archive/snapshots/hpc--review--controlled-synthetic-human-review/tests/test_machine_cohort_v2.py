from __future__ import annotations

from scripts.finalize_v2_machine_cohort import (
    RETIRED,
    SELECTED,
    UNUSED_RESERVES,
    manifest,
)


def test_selection_is_exactly_twenty_and_never_uses_retired_ids():
    ids = [row[0] for row in SELECTED]
    assert len(ids) == len(set(ids)) == 20
    assert set(ids).isdisjoint(RETIRED)
    assert {family_id for family_id in ids if family_id.startswith("R")} == {"R01", "R02"}


def test_unused_reserves_were_not_run():
    assert UNUSED_RESERVES == ("R03", "R04", "R05")


def test_manifest_revalidates_complete_unique_cohort():
    value, accepted = manifest()
    assert value["family_count"] == 20
    assert value["machine_accept_count"] == 20
    assert value["fresh_revalidation_pass_count"] == 20
    assert value["unique_mechanism_count"] == 20
    assert value["duplicate_candidate_hashes"] == 0
    assert len(accepted) == 100
    assert value["human_blinded_review"] == "PENDING"
