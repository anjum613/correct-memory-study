"""Behavioral public feature checks for X04."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x04_existing(app)
    checks.x04_feature(app)
