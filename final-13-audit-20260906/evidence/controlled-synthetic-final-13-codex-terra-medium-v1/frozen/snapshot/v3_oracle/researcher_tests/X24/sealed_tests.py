"""Researcher-only sealed behavioral observer for X24."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x24_target_invariant(app)
