"""Behavioral public feature checks for X03."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x03_existing(app)
    checks.x03_feature(app)
