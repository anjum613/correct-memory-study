import pytest

from counter_state import CounterState, replay


def test_increment_sequence_accumulates():
    assert replay([
        {"type": "increment", "amount": 4},
        {"type": "increment", "amount": -1},
    ]).value == 3


def test_disable_blocks_increment_until_enabled():
    result = replay([
        {"type": "increment", "amount": 2},
        {"type": "disable"},
        {"type": "increment", "amount": 100},
        {"type": "enable"},
        {"type": "increment", "amount": 3},
    ])
    assert result == CounterState(value=5, enabled=True)


def test_initial_state_flows_through_events():
    initial = CounterState(value=7, enabled=False)
    assert replay([{"type": "increment", "amount": 9}], initial) == initial


def test_empty_replay_returns_initial_state():
    initial = CounterState(value=8)
    assert replay([], initial) is initial


def test_unknown_event_is_not_silently_ignored():
    with pytest.raises(ValueError):
        replay([{"type": "reset"}])
