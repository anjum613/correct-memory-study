"""Behavioral public feature checks for X07."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x07_existing(app)
    checks.x07_feature(app)
