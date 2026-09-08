"""Evaluate all applicable rules using deny-overrides precedence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str


def run(policy_rules, resource, effect_sink):
    matched = []
    has_allow = False
    has_deny = False
    for name, effect, selector in policy_rules:
        if selector == '*' or selector == resource:
            matched.append(name)
            if effect == 'deny':
                has_deny = True
            elif effect == 'allow':
                has_allow = True

    explanation = tuple(matched)
    if has_deny:
        return X21Decision('deny', explanation, 'explicit-deny')
    if has_allow:
        effect_sink.append(resource)
        return X21Decision('allow', explanation, 'explicit-allow')
    return X21Decision('deny', explanation, 'default-deny')
