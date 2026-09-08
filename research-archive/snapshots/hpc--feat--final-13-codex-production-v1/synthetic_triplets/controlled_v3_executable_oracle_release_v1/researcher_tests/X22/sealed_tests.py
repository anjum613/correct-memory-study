"""Researcher-only sealed behavioral observer for X22."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x22_target_invariant(app)
