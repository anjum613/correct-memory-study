"""Completion callbacks with only the permitted extension operations."""


def _append_operation(destination):
    # Capture only the destination's append operation, never the context or
    # any callable returned by its unrestricted reference provider.
    append = destination.append

    def operation(value):
        append(value)
        return "ok"

    return operation


def run(context, ordered_callbacks):
    results = []
    notify = None
    observe = None
    for callback in ordered_callbacks:
        if notify is None:
            notify = _append_operation(context.notifications)
            observe = _append_operation(context.observations)
        # Each callback owns its mapping; edits cannot affect later callbacks.
        # The two operations remain usable after either return or failure.
        references = {"notify": notify, "observe": observe}
        try:
            results.append(callback.invoke(references))
        except Exception:
            results.append("callback-error")
    return results
