"""Behavioral public feature checks for X13."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x13_existing(app)
    checks.x13_feature(app)
