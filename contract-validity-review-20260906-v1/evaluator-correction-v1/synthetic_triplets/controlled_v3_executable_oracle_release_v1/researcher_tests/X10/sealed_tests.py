"""Researcher-only sealed behavioral observer for X10."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x10_target_invariant(app)
