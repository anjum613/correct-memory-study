from intervals import merge_intervals


def test_touching_boundaries_merge():
    assert merge_intervals([(1, 2), (2, 4)]) == [(1, 4)]


def test_nested_and_touching_chain_merges():
    assert merge_intervals([(5, 8), (1, 10), (10, 12)]) == [(1, 12)]


def test_negative_intervals_are_sorted_and_merged():
    assert merge_intervals([(-2, 0), (-5, -2), (3, 4)]) == [(-5, 0), (3, 4)]


def test_input_order_is_not_mutated():
    original = [(8, 9), (1, 3), (3, 5)]
    snapshot = list(original)
    merge_intervals(original)
    assert original == snapshot


def test_empty_input_is_supported():
    assert merge_intervals([]) == []
