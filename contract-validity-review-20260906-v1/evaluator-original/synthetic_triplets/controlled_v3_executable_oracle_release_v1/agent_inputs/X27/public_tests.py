"""Behavioral public feature checks for X27."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x27_existing(app)
    checks.x27_feature(app)
