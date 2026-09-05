"""Researcher-only sealed behavioral observer for X12."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x12_target_invariant(app)
