"""Utilities for inclusive integer intervals."""


def merge_intervals(intervals):
    """Return sorted inclusive intervals with overlaps coalesced."""
    ordered = sorted((start, end) for start, end in intervals)
    if not ordered:
        return []

    merged = [ordered[0]]
    for start, end in ordered[1:]:
        current_start, current_end = merged[-1]
        if start < current_end:
            merged[-1] = (current_start, max(current_end, end))
        else:
            merged.append((start, end))
    return merged
