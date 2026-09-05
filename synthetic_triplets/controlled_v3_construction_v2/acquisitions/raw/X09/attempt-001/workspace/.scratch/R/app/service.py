"""Commit each authenticated operation once and return ('ack', operation_id).

Receipts belong to the store and bind an identity to a snapshot of its meaning.
A conflicting reuse raises ValueError. A lost acknowledgment can be retried.
"""
from copy import deepcopy
from threading import RLock


# Serialize commits to the in-memory store, including receipt publication.
_commit_lock = RLock()


def _receipt(store, operation_id, value):
    if operation_id not in store.receipts:
        return None
    recorded_meaning, result = store.receipts[operation_id]
    if recorded_meaning != value:
        raise ValueError('operation identity already bound to different meaning')
    return result


def run(operation_store, operation_id, meaning, fault=None):
    value = deepcopy(meaning)
    with _commit_lock:
        previous = _receipt(operation_store, operation_id, value)
        if previous is not None:
            return previous

    # The hook may synchronize concurrent callers. Recheck after it returns.
    if operation_store.before_commit is not None:
        operation_store.before_commit()
    if fault == 'before_commit':
        raise RuntimeError('before_commit')

    with _commit_lock:
        previous = _receipt(operation_store, operation_id, value)
        if previous is not None:
            return previous
        result = ('ack', operation_id)
        original_length = len(operation_store.effects)
        try:
            operation_store.effects.append((operation_id, deepcopy(value)))
            if fault == 'after_effect':
                raise RuntimeError('after_effect')
            operation_store.receipts[operation_id] = (value, result)
        except BaseException:
            # Roll back the uncommitted effect and any partial receipt.
            del operation_store.effects[original_length:]
            operation_store.receipts.pop(operation_id, None)
            raise

    if fault == 'after_commit':
        raise RuntimeError('after_commit')
    return result
