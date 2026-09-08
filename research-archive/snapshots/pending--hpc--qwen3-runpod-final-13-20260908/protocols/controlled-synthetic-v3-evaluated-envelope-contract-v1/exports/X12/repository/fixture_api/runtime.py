from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class X12Result:
    exit_code: int
    output: tuple

class X12Child:

    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.effects = []
        self.environments = []

    def run(self, environment):
        environment = dict(environment)
        self.environments.append(environment)
        if environment.get('LOCAL_INIT') == 'append' or environment.get('PYTHONPATH'):
            self.effects.append('authority-change')
        return X12Result(self.exit_code, tuple((environment[name] for name in ('LOCALE', 'DATA', 'TUNING', 'REQUIRED'))))
