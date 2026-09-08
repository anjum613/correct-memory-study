from __future__ import annotations

from pathlib import Path

import scripts.freeze_controlled_v2_release as release


def test_release_inventory_includes_all_frozen_scientific_inputs():
    paths = {path.relative_to(release.REPO_ROOT).as_posix() for path in release.released_paths()}
    assert "synthetic_triplets/controlled_v2/cohort_plan.json" in paths
    assert "synthetic_triplets/controlled_v2/generator_prompt.md" in paths
    assert "synthetic_triplets/controlled_v2/evaluation_protocol_template.json" in paths
    assert "scripts/validate_controlled_triplet_v2.py" in paths
    assert "scripts/verify_controlled_v2_reference_matrix.py" in paths
    assert "scripts/run_controlled_v2_constructors.py" in paths
    assert "tests/test_controlled_v2_validator.py" in paths
    assert all(
        f"synthetic_triplets/controlled_v2/family_specs/F{index:02d}.json" in paths
        for index in range(1, 21)
    )


def test_release_inventory_excludes_future_outputs(tmp_path: Path, monkeypatch):
    # The path-level rule is independent of whether acquisitions have been run.
    candidate = release.COHORT_ROOT / "acquisitions/raw/F01/attempt-001/candidate.txt"
    review = release.COHORT_ROOT / "reviews/F01.json"
    assert all(
        not path.is_relative_to(release.COHORT_ROOT / "acquisitions")
        and not path.is_relative_to(release.COHORT_ROOT / "reviews")
        for path in release.released_paths()
    )
    assert candidate not in release.released_paths()
    assert review not in release.released_paths()


def test_inventory_digest_is_order_stable():
    files = release.inventory()
    reversed_files = dict(reversed(list(files.items())))
    assert release.inventory_sha256(files) == release.inventory_sha256(reversed_files)
