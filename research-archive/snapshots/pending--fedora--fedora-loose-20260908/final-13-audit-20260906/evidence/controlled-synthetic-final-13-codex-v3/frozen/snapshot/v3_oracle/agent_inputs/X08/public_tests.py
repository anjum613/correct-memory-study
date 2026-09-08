"""Behavioral public feature checks for X08."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x08_existing(app)
    checks.x08_feature(app)
