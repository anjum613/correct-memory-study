"""Behavioral public feature checks for X17."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x17_existing(app)
    checks.x17_feature(app)
