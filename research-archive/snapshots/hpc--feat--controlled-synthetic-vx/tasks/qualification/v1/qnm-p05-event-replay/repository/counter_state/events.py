from dataclasses import replace

from .model import CounterState


def apply_event(state: CounterState, event: dict) -> CounterState:
    event_type = event.get("type")
    if event_type == "increment":
        if not state.enabled:
            return state
        return replace(state, value=state.value + int(event.get("amount", 1)))
    if event_type == "disable":
        return replace(state, enabled=False)
    if event_type == "enable":
        return replace(state, enabled=True)
    raise ValueError(f"unknown counter event: {event_type!r}")
