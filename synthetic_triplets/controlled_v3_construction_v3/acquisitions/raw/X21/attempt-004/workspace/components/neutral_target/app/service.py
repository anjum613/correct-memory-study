"""Policy evaluation for requests with at most one applicable rule."""

from dataclasses import dataclass


@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str


def run(policy_rules, resource, effect_sink):
    applicable = [
        (name, effect)
        for name, effect, selector in policy_rules
        if selector == '*' or selector == resource
    ]
    if len(applicable) > 1:
        raise ValueError('Overlapping policy rules are not supported')
    if not applicable:
        return X21Decision('deny', (), 'default-deny')
    name, effect = applicable[0]
    if effect == 'deny':
        return X21Decision('deny', (name,), 'explicit-deny')
    if effect == 'allow':
        effect_sink.append(resource)
        return X21Decision('allow', (name,), 'explicit-allow')
    return X21Decision('deny', (name,), 'default-deny')
