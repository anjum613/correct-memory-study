"""Baseline with extension execution unavailable."""


def run(context, ordered_callbacks):
    for callback in ordered_callbacks:
        raise NotImplementedError("Extension callbacks are unavailable")
    return []
