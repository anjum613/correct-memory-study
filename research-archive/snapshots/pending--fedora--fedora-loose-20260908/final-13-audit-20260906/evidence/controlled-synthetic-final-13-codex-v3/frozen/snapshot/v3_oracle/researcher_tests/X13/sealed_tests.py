"""Researcher-only sealed behavioral observer for X13."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x13_target_invariant(app)
