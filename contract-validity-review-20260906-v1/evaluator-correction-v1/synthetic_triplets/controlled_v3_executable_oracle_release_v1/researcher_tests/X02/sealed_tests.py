"""Researcher-only sealed behavioral observer for X02."""
from ... import sealed_new as checks

def run_sealed(app):
    checks.x02_target(app)
