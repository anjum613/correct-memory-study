"""Invoke extensions with only their permitted event operations."""


def _event_operation(events):
    # Capture only the append operation, never the producer context or its
    # full reference tree. Captured operations remain usable after invocation.
    append = events.append

    def record(value):
        append(value)
        return "ok"

    return record


def run(context, ordered_callbacks):
    notify = _event_operation(context.notifications)
    observe = _event_operation(context.observations)
    results = []
    for callback in ordered_callbacks:
        # Each callback gets its own mapping so edits cannot affect later
        # callbacks. Neither permitted operation retains producer authority.
        references = {"notify": notify, "observe": observe}
        try:
            results.append(callback.invoke(references))
        except Exception:
            results.append("callback-error")
    return results
