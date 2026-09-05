"""Completion callbacks with only the documented extension authority."""


def _action(destination):
    # Capture the destination's append operation, never the producer context
    # or an operation returned by full_references (which closes over it).
    append = destination.append

    def perform(value):
        append(value)
        return 'ok'

    return perform


def run(context, ordered_callbacks):
    results = []
    for callback in ordered_callbacks:
        # Each callback owns its mapping. Captured actions remain usable after
        # completion, including when the callback raises an ordinary error.
        references = {
            'notify': _action(context.notifications),
            'observe': _action(context.observations),
        }
        try:
            results.append(callback.invoke(references))
        except Exception:
            results.append('callback-error')
    return results
