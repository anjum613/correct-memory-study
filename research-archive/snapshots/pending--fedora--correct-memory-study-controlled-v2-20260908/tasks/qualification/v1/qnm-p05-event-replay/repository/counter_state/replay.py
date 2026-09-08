from .events import apply_event
from .model import CounterState


def replay(events, initial: CounterState | None = None) -> CounterState:
    state = initial or CounterState()
    for event in events:
        apply_event(state, event)
    return state
