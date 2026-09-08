"""Behavioral public feature checks for X01."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x01_existing(app)
    checks.x01_feature(app)
