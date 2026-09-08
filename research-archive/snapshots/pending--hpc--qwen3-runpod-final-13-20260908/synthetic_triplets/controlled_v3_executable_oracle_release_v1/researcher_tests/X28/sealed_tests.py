"""Researcher-only sealed behavioral observer for X28."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x28_target_invariant(app)
