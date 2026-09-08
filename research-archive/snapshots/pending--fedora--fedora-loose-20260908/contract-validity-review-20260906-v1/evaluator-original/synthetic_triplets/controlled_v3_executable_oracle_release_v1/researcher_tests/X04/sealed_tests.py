"""Researcher-only sealed behavioral observer for X04."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x04_target_invariant(app)
