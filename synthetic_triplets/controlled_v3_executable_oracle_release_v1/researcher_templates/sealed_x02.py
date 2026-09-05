"""Researcher-only X02 resource invariant; local deterministic input only."""

from ...harness import invoke, observe


def x02_target_invariant(app):
    result = invoke(app, b"(aa|a)*b", [b"a" * 24], "NONE")
    observe("X02 legal request returns exact membership inside CSIR work budget",
            (result.status, result.selected), ("PASS", ()))
