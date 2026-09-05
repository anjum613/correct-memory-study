"""Benign public integration fixture: collects normal calls/results only. It is not an implementation of the deployment's execution semantics."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class X12Result:
    exit_code: int
    output: tuple

class X12Child:

    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.environments = []

    def run(self, environment):
        environment = dict(environment)
        self.environments.append(environment)
        return X12Result(self.exit_code, tuple((environment[name] for name in ('LOCALE', 'DATA', 'TUNING', 'REQUIRED'))))
