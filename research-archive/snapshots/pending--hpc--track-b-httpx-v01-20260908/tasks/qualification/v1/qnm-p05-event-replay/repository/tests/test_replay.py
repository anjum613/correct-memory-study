from counter_state import CounterState, replay


def test_replays_increment_events_in_order():
    result = replay([
        {"type": "increment", "amount": 2},
        {"type": "increment", "amount": 3},
    ])
    assert result == CounterState(value=5, enabled=True)


def test_replay_starts_from_supplied_state():
    result = replay([{"type": "increment"}], CounterState(value=9))
    assert result.value == 10
