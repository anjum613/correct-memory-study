"""Researcher-only sealed behavioral observer for X16."""
from ... import checks_b as checks

def run_sealed(app):
    checks.x16_target_invariant(app)
