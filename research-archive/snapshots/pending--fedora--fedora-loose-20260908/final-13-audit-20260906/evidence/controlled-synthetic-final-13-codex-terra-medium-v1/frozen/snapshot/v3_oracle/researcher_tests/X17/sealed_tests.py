"""Researcher-only sealed behavioral observer for X17."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x17_target_invariant(app)
