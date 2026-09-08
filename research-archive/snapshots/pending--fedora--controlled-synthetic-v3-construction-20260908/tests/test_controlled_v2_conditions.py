from __future__ import annotations

from scripts.build_controlled_v2_condition_envelopes import (
    BOUNDARY_SENTENCE,
    CONDITIONS,
    ENVELOPE_BYTES,
    IRRELEVANT_PAIRING,
    render_envelope,
    semantic_content,
)
from scripts.controlled_v2_catalog import FAMILIES, FAMILY_BY_ID


def test_condition_names_are_exactly_the_frozen_four():
    assert CONDITIONS == (
        "NO_MEMORY",
        "SOURCE_CORRECT_MEMORY",
        "MATCHED_IRRELEVANT_MEMORY",
        "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
    )


def test_irrelevant_pairing_is_a_complete_derangement_across_mechanisms():
    ids = {item.family_id for item in FAMILIES}
    assert set(IRRELEVANT_PAIRING) == ids
    assert set(IRRELEVANT_PAIRING.values()) == ids
    for source, paired in IRRELEVANT_PAIRING.items():
        assert source != paired
        assert FAMILY_BY_ID[source].mechanism != FAMILY_BY_ID[paired].mechanism


def test_all_condition_envelopes_have_identical_byte_length_and_placement():
    for item in FAMILIES:
        rendered = [render_envelope(item.family_id, condition) for condition in CONDITIONS]
        assert {len(value.encode("ascii")) for value in rendered} == {ENVELOPE_BYTES}
        assert all(value.startswith("[BEGIN_MEMORY_CONTEXT]\n") for value in rendered)
        assert all(value.endswith("\n[END_MEMORY_CONTEXT]\n") for value in rendered)


def test_relevant_memory_is_exact_source_memory_and_boundary_adds_only_one_statement():
    for item in FAMILIES:
        relevant = semantic_content(item.family_id, "SOURCE_CORRECT_MEMORY")
        boundary = semantic_content(
            item.family_id, "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY"
        )
        assert relevant == item.source_memory.rstrip()
        assert boundary == relevant + "\n\nApplicability boundary\n" + BOUNDARY_SENTENCE
        assert boundary.count(BOUNDARY_SENTENCE) == 1


def test_irrelevant_memory_preserves_source_memory_format():
    headings = (
        "Source task\n",
        "Reusable procedure\n",
        "Why it was correct in the source\n",
        "Implementation steps\n",
    )
    for item in FAMILIES:
        irrelevant = semantic_content(item.family_id, "MATCHED_IRRELEVANT_MEMORY")
        paired = FAMILY_BY_ID[IRRELEVANT_PAIRING[item.family_id]]
        assert irrelevant == paired.source_memory.rstrip()
        assert all(heading in irrelevant for heading in headings)
