"""Researcher-only sealed behavioral observer for X26."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x26_target_invariant(app)
