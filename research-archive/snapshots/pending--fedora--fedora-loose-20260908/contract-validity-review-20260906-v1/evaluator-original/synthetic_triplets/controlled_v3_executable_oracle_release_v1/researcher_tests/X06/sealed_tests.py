"""Researcher-only sealed behavioral observer for X06."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x06_target_invariant(app)
