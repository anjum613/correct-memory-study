"""Metadata-only preparation for the frozen V2 matcher at confirmatory screening."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping, Sequence


_INSTANCE = re.compile(r"^([A-Za-z0-9.-]+)__(.+)_([0-9a-f]{40})$")


class ConfirmatoryPairingV2Error(ValueError):
    """Confirmatory metadata cannot be prepared without ambiguity."""


def canonical_repository_url_from_instance_id(instance_id: str) -> str:
    """Derive repository identity without reading target code or oracle material."""

    match = _INSTANCE.fullmatch(instance_id)
    if not match:
        raise ConfirmatoryPairingV2Error("invalid SusVibes instance ID")
    owner, repository, _anchor = match.groups()
    return f"https://github.com/{owner}/{repository}.git".casefold()


def source_tier_for_target(
    entry: Mapping[str, Any], *, target_instance_id: str
) -> str:
    """Return S1 for same-repository experience and S2 for the frozen ecosystem."""

    target_url = canonical_repository_url_from_instance_id(target_instance_id)
    source_url = str(entry.get("repository_url", "")).casefold()
    if not source_url:
        raise ConfirmatoryPairingV2Error("source repository identity is absent")
    if not source_url.endswith(".git"):
        source_url += ".git"
    return "S1" if source_url == target_url else "S2"


def prepare_frozen_corpus_for_target(
    entries: Sequence[Mapping[str, Any]], *, target_instance_id: str
) -> list[dict[str, Any]]:
    """Add only the target-specific tier required by the unchanged matcher API."""

    prepared: list[dict[str, Any]] = []
    for original in entries:
        entry = deepcopy(dict(original))
        tiers = dict(entry.get("source_tier_by_target", {}))
        tiers[target_instance_id] = source_tier_for_target(
            entry, target_instance_id=target_instance_id
        )
        entry["source_tier_by_target"] = tiers
        prepared.append(entry)
    return prepared
