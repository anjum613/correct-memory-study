"""Researcher-only sealed behavioral observer for X14."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x14_target_invariant(app)
