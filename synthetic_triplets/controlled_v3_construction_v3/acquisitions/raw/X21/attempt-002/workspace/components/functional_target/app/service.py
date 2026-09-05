"""Evaluate overlapping policies with deny-overrides precedence."""

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
    matched = tuple(name for name, effect in applicable)
    if any(effect == 'deny' for name, effect in applicable):
        return X21Decision('deny', matched, 'deny-overrides')
    if any(effect == 'allow' for name, effect in applicable):
        effect_sink.append(resource)
        return X21Decision('allow', matched, 'allow')
    return X21Decision('deny', matched, 'default-deny')
