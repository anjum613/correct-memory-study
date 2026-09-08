"""Behavioral public feature checks for X23."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x23_existing(app)
    checks.x23_feature(app)
