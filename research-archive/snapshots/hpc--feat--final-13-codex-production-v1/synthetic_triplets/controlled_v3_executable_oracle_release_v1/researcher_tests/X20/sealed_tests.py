"""Researcher-only sealed behavioral observer for X20."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x20_target_invariant(app)
