"""Behavioral public feature checks for X21."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x21_existing(app)
    checks.x21_feature(app)
