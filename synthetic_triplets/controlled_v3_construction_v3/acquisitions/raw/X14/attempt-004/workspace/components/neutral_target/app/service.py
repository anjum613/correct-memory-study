"""Baseline with independently authored callbacks unavailable."""


def run(context, ordered_callbacks):
    results = []
    for callback in ordered_callbacks:
        raise NotImplementedError("Extension callbacks are unavailable")
    return results
