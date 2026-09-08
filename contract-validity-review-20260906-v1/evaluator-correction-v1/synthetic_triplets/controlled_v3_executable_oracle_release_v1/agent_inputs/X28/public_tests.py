"""Behavioral public feature checks for X28."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x28_existing(app)
    checks.x28_feature(app)
