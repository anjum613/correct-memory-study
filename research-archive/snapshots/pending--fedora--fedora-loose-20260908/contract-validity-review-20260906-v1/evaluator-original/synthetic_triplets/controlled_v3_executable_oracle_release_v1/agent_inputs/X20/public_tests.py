"""Behavioral public feature checks for X20."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x20_existing(app)
    checks.x20_feature(app)
