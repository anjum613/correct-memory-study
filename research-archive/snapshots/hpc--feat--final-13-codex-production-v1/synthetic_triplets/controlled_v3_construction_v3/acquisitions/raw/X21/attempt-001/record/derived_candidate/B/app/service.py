"""Disjoint-rule baseline; overlapping policies are unavailable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str


def run(policy_rules, resource, effect_sink):
    matches = [
        (name, effect)
        for name, effect, selector in policy_rules
        if selector == '*' or selector == resource
    ]
    if len(matches) > 1:
        raise ValueError('Overlapping policy rules are unavailable')
    if not matches:
        return X21Decision('deny', (), 'default-deny')
    name, effect = matches[0]
    if effect == 'allow':
        effect_sink.append(resource)
    return X21Decision(
        effect, (name,), 'deny-overrides' if effect == 'deny' else 'allow'
    )
