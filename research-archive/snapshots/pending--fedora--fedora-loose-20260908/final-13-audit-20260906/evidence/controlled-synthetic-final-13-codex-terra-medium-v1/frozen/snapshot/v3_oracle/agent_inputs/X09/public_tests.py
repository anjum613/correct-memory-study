"""Behavioral public feature checks for X09."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x09_existing(app)
    checks.x09_feature(app)
