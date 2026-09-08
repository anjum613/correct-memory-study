def validated_counts(values):
    if any(value < 0 for value in values):
        raise ValueError("counts must be non-negative")
    return tuple(values)
