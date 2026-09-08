from __future__ import annotations

import pytest

from cmpilot.source_pairing_confirmatory_v2 import (
    ConfirmatoryPairingV2Error,
    canonical_repository_url_from_instance_id,
    prepare_frozen_corpus_for_target,
    source_tier_for_target,
)


TARGET = "encode__starlette_1797de464124b090f10cf570441e8292936d63e3"


def test_repository_tier_is_derived_from_instance_id_only() -> None:
    same = {"repository_url": "https://github.com/encode/starlette.git"}
    other = {"repository_url": "https://github.com/django/django.git"}
    assert canonical_repository_url_from_instance_id(TARGET) == (
        "https://github.com/encode/starlette.git"
    )
    assert source_tier_for_target(same, target_instance_id=TARGET) == "S1"
    assert source_tier_for_target(other, target_instance_id=TARGET) == "S2"


def test_preparation_does_not_mutate_frozen_entry() -> None:
    original = {
        "source_id": "src-example",
        "repository_url": "https://github.com/encode/starlette.git",
        "source_tier_by_target": {"development": "S2"},
    }
    prepared = prepare_frozen_corpus_for_target(
        [original], target_instance_id=TARGET
    )
    assert original["source_tier_by_target"] == {"development": "S2"}
    assert prepared[0]["source_tier_by_target"][TARGET] == "S1"


def test_invalid_instance_id_fails_closed() -> None:
    with pytest.raises(ConfirmatoryPairingV2Error):
        canonical_repository_url_from_instance_id("not-an-instance")
