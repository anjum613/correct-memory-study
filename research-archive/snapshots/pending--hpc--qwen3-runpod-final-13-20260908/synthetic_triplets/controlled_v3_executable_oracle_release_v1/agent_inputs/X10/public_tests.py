"""Behavioral public feature checks for X10."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x10_existing(app)
    checks.x10_feature(app)
