from __future__ import annotations


def accumulate_metric(samples: list[int]) -> int:
    total = 0
    for sample in samples:
        if not isinstance(sample, int):
            raise TypeError("metric samples must be integers")
        total += sample
    return total
