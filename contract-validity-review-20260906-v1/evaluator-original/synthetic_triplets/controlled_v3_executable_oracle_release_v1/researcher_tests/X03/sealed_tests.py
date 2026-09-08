"""Researcher-only sealed behavioral observer for X03."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x03_target_invariant(app)
