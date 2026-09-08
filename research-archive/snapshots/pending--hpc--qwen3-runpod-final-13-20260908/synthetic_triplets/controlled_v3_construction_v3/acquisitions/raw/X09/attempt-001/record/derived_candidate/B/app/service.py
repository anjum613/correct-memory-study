"""Ordinary operation processing; each delivery creates an effect."""
from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    effect = (operation_id, deepcopy(meaning))
    if fault in ('before_effect', 'before_commit'):
        raise RuntimeError(fault)
    hook = operation_store.before_commit
    if hook is not None:
        hook()
    operation_store.effects.append(effect)
    if fault in ('after_effect', 'after_commit', 'after_receipt'):
        raise RuntimeError(fault)
    return ('ack', operation_id, len(operation_store.effects))
