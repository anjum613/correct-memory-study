"""Process authenticated operations and return stable acknowledgments.

The documented acknowledgment is ('ack', operation_id). Delivery is assumed
at most once; the acknowledgment does not depend on other operations.
"""
from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    value = deepcopy(meaning)
    if operation_store.before_commit is not None:
        operation_store.before_commit()
    if fault == 'before_commit':
        raise RuntimeError('before_commit')
    operation_store.effects.append((operation_id, value))
    if fault in ('after_effect', 'after_commit'):
        raise RuntimeError(fault)
    return ('ack', operation_id)
