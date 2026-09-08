"""Commit each operation once and return its original acknowledgment on retry.

An operation ID is bound to a snapshot of its authorized meaning. Reusing an
ID with a different meaning raises ValueError. Acknowledgments are tuples
('ack', operation_id, effect_count_at_commit). Receipts live in the supplied
store, so constructing another service instance does not discard them.
"""
from copy import deepcopy


def _retry(receipt, meaning):
    if receipt["meaning"] != meaning:
        raise ValueError("operation ID already bound to a different meaning")
    # Another delivery can observe the reservation while its owner commits.
    # No callbacks or injected failures occur within this short commit window.
    while not receipt["committed"]:
        pass
    if receipt["committed"] == "failed":
        raise RuntimeError("concurrent commit failed; retry the operation")
    return receipt["result"]


def run(operation_store, operation_id, meaning, fault=None):
    snapshot = deepcopy(meaning)
    receipts = operation_store.receipts
    if operation_id in receipts:
        return _retry(receipts[operation_id], snapshot)

    if fault == "before_commit":
        raise RuntimeError("before_commit")
    hook = operation_store.before_commit
    if hook is not None:
        operation_store.before_commit = None
        hook()

    effect = (operation_id, deepcopy(snapshot))
    candidate = {"meaning": snapshot, "result": None, "committed": False}
    # setdefault arbitrates deliveries atomically on the public Python dict.
    # Reentrant deliveries from before_commit participate in the same table.
    receipt = receipts.setdefault(operation_id, candidate)
    if receipt is not candidate:
        return _retry(receipt, snapshot)

    try:
        operation_store.effects.append(effect)
    except BaseException:
        # An unsuccessful append leaves the operation available for retry.
        # The public effects list has the ordinary atomic append contract.
        del receipts[operation_id]
        candidate["result"] = None
        candidate["committed"] = "failed"
        raise
    candidate["result"] = ("ack", operation_id, len(operation_store.effects))
    candidate["committed"] = True

    # Model a lost acknowledgment only after both the effect and receipt exist.
    if fault in ("after_effect", "before_receipt", "after_commit", "after_receipt"):
        raise RuntimeError(fault)
    return candidate["result"]
