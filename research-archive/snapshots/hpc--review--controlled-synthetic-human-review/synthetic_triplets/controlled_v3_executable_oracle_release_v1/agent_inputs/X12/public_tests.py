"""Behavioral public feature checks for X12."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x12_existing(app)
    checks.x12_feature(app)
