"""Evaluate exact and wildcard policies using deny-overrides precedence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str


def run(policy_rules, resource, effect_sink):
    """Report matching rule names in canonical order and apply an allow once.

    Explanations are 'deny-overrides' for a matching deny, 'allow' for an
    unopposed allow, and 'default-deny' when no rule permits the operation.
    """
    matches = [
        (name, effect)
        for name, effect, selector in policy_rules
        if selector == '*' or selector == resource
    ]
    matched = tuple(sorted(name for name, effect in matches))
    if any(effect == 'deny' for name, effect in matches):
        return X21Decision('deny', matched, 'deny-overrides')
    if any(effect == 'allow' for name, effect in matches):
        effect_sink.append(resource)
        return X21Decision('allow', matched, 'allow')
    return X21Decision('deny', matched, 'default-deny')
