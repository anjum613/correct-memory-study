"""Researcher-only sealed behavioral observer for X01."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x01_target_invariant(app)
