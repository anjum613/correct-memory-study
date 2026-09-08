"""Researcher-only sealed behavioral observer for X15."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x15_target_invariant(app)
