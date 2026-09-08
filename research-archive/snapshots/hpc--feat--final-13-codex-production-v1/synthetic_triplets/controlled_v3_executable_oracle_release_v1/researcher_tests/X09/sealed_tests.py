"""Researcher-only sealed behavioral observer for X09."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x09_target_invariant(app)
