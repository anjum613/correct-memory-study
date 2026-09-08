"""Researcher-only sealed behavioral observer for X21."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x21_target_invariant(app)
