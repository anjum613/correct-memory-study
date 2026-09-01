from pathlib import Path

from scripts import v2_control_matrix as matrix


ROOT = Path(__file__).parents[1]


def test_all_six_families_have_a_source() -> None:
    assert len(matrix.FAMILIES) == 6
    for family in matrix.FAMILIES:
        assert matrix.HISTORICAL_FAMILY_ROOTS.get(
            family, ROOT / "families" / family
        ).is_dir()


def test_historical_sources_are_never_outputs() -> None:
    assert matrix.OUTPUT.is_relative_to(ROOT)
    for path in matrix.HISTORICAL_FAMILY_ROOTS.values():
        assert not path.is_relative_to(ROOT)


def test_axios_uses_the_exact_qualified_node() -> None:
    assert matrix.AXIOS_NODE.is_file()
    assert matrix._sha256_file(matrix.AXIOS_NODE) == (
        "650356ce523cc01dee7b7e9f776b195d8601898af42bbe00c66a94a056698b03"
    )
