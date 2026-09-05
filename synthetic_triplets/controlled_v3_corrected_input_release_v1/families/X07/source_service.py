"""Executable source-procedure scaffold."""
def run(value, *, source_assumption=True):
    if not source_assumption:
        raise ValueError("source applicability assumption is false")
    return {"family": 'X07', "value": value, "source": True}
