from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str

def _x21_match(selector, resource):
    return selector == '*' or selector == resource

def _x21_apply(effect, resource, effects):
    if effect == 'allow':
        effects.append(resource)
