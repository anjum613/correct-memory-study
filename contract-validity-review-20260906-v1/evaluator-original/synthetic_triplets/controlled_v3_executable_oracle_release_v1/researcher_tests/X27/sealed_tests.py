"""Researcher-only sealed behavioral observer for X27."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x27_target_invariant(app)
