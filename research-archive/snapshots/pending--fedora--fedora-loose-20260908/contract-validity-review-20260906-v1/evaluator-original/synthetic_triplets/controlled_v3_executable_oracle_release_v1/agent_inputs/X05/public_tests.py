"""Behavioral public feature checks for X05."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x05_existing(app)
    checks.x05_feature(app)
