"""Researcher-only sealed behavioral observer for X23."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x23_target_invariant(app)
