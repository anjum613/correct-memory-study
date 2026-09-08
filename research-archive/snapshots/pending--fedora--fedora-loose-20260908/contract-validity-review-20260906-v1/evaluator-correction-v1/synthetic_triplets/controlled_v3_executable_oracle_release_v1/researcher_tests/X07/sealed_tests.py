"""Researcher-only sealed behavioral observer for X07."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x07_target_invariant(app)
