"""Ordinary delivery processing, without retry deduplication."""
from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    effect = (operation_id, deepcopy(meaning))
    if fault == "before_commit":
        raise RuntimeError("before_commit")
    hook = operation_store.before_commit
    if hook is not None:
        operation_store.before_commit = None
        hook()
    operation_store.effects.append(effect)
    result = ("ack", operation_id, len(operation_store.effects))
    if fault in ("after_effect", "before_receipt", "after_commit", "after_receipt"):
        raise RuntimeError(fault)
    return result
