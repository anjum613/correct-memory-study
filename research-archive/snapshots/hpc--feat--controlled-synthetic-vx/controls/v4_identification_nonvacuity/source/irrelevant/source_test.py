from metric_accumulator import accumulate_metric


assert accumulate_metric([3, 4, 5]) == 12
assert accumulate_metric([]) == 0
