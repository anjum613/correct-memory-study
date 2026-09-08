"""Behavioral public feature checks for X26."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x26_existing(app)
    checks.x26_feature(app)
