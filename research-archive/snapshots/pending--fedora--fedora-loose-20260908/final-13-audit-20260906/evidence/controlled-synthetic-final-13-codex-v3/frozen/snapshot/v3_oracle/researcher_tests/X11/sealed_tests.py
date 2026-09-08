"""Researcher-only sealed behavioral observer for X11."""
from ... import checks_a as checks

def run_sealed(app):
    checks.x11_target_invariant(app)
