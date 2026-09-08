"""Behavioral public feature checks for X24."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x24_existing(app)
    checks.x24_feature(app)
