"""Return a stable acknowledgment for each authenticated operation identity.

The acknowledgment is ('ack', operation_id). Delivery remains at most once.
"""
from copy import deepcopy


def run(operation_store, operation_id, meaning, fault=None):
    record = (operation_id, deepcopy(meaning))
    if operation_store.before_commit is not None:
        operation_store.before_commit()
    if fault == 'before_commit':
        raise RuntimeError('before_commit')
    operation_store.effects.append(record)
    if fault in ('after_effect', 'after_commit'):
        raise RuntimeError(fault)
    return ('ack', operation_id)
