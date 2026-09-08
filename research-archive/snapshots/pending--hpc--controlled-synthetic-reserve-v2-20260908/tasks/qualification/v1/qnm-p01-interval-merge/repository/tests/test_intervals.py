from intervals import merge_intervals


def test_merges_overlapping_intervals():
    assert merge_intervals([(1, 4), (3, 6)]) == [(1, 6)]


def test_merges_touching_inclusive_intervals():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]


def test_sorts_disjoint_intervals():
    assert merge_intervals([(8, 9), (1, 2)]) == [(1, 2), (8, 9)]
