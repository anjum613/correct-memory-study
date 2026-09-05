"""Commit each authenticated identity once, bound to its original meaning.

The acknowledgment is ('ack', operation_id). A conflicting meaning raises
ValueError. The store's committed effect log is authoritative; receipts are
rebuildable indexes, so interruption after commit cannot repeat an effect.
"""
from copy import deepcopy
from threading import RLock


_LOCK_CREATION = RLock()


def _lock(store):
    with _LOCK_CREATION:
        if not hasattr(store, '_operation_commit_lock'):
            store._operation_commit_lock = RLock()
        return store._operation_commit_lock


def _committed(store, operation_id, meaning):
    for saved_id, saved_meaning in store.effects:
        if saved_id == operation_id:
            if saved_meaning != meaning:
                raise ValueError('operation identity already bound to another meaning')
            return True
    return False


def run(operation_store, operation_id, meaning, fault=None):
    # Snapshot caller-owned data before publishing the effect.
    record = (deepcopy(operation_id), deepcopy(meaning))
    operation_id, meaning = record
    result = ('ack', operation_id)
    lock = _lock(operation_store)
    with lock:
        if _committed(operation_store, operation_id, meaning):
            operation_store.receipts[operation_id] = result
            return result

    # Hooks may synchronize competing callers. Never hold the commit lock
    # while invoking external code; recheck identity afterward.
    if operation_store.before_commit is not None:
        operation_store.before_commit()
    if fault == 'before_commit':
        raise RuntimeError('before_commit')
    with lock:
        if _committed(operation_store, operation_id, meaning):
            operation_store.receipts[operation_id] = result
            return result
        # This single append is the commit point in the provided store API.
        # Identity and authorized meaning are part of the effect itself.
        operation_store.effects.append(record)
        if fault == 'after_effect':
            raise RuntimeError('after_effect')
        operation_store.receipts[operation_id] = result
        if fault == 'after_commit':
            raise RuntimeError('after_commit')
        return result
