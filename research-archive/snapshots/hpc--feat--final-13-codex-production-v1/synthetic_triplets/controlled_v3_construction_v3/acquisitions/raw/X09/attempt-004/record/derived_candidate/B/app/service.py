"""Ordinary processing for operations delivered at most once."""

from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    if fault == "before_commit":
        raise RuntimeError("failure before commit")
    hook = operation_store.before_commit
    if hook is not None:
        operation_store.before_commit = None
        hook()
    operation_store.effects.append((operation_id, deepcopy(meaning)))
    acknowledgment = ("ack", operation_id, len(operation_store.effects))
    if fault in ("after_effect", "after_commit", "before_ack", "after_receipt"):
        raise RuntimeError("acknowledgment lost after commit")
    return acknowledgment
