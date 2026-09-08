"""Researcher-only sealed behavioral observer for X18."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x18_target_invariant(app)
