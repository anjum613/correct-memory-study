"""Researcher-only sealed behavioral observer for X08."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x08_target_invariant(app)
