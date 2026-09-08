"""Completion callbacks with observation and notification authority only."""


def _append_action(destination):
    # Capture the permitted destination, never the producer context or its
    # full reference graph. Captured actions remain valid after completion.
    append = destination.append

    def action(value):
        append(value)
        return "ok"

    return action


def run(context, ordered_callbacks):
    results = []
    for callback in ordered_callbacks:
        try:
            # Each callback owns its mapping. Changes to it cannot change
            # which actions a later callback receives.
            references = {
                "notify": _append_action(context.notifications),
                "observe": _append_action(context.observations),
            }
            results.append(callback.invoke(references))
        except Exception:
            results.append("callback-error")
    return results
