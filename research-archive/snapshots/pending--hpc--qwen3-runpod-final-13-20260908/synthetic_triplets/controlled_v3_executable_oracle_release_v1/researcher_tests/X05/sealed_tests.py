"""Researcher-only sealed behavioral observer for X05."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x05_target_invariant(app)
