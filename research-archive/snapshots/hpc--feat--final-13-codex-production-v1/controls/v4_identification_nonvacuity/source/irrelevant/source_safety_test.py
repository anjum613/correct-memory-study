from metric_accumulator import accumulate_metric


samples = [1, 2, 3]
assert accumulate_metric(samples) == 6
assert samples == [1, 2, 3]
