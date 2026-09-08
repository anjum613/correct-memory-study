"""Behavioral public feature checks for X14."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x14_existing(app)
    checks.x14_feature(app)
