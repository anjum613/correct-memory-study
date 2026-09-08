from dataclasses import dataclass


@dataclass(frozen=True)
class CounterState:
    value: int = 0
    enabled: bool = True
