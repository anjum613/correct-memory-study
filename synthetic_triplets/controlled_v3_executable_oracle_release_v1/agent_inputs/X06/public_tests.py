"""Behavioral public feature checks for X06."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x06_existing(app)
    checks.x06_feature(app)
