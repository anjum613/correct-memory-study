"""Ordinary delivery processing, without retry suppression."""
from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    snapshot = deepcopy(meaning)
    hook = operation_store.before_commit
    if hook is not None:
        hook()
    if fault in ('before_effect', 'before_commit'):
        raise RuntimeError('operation interrupted before commit')
    operation_store.effects.append((operation_id, snapshot))
    result = ('ack', operation_id, len(operation_store.effects))
    if fault in ('after_effect', 'after_commit', 'after_receipt'):
        raise RuntimeError('operation committed; acknowledgment interrupted')
    return result
