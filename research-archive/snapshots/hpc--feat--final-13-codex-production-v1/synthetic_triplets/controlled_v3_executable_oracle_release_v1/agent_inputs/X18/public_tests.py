"""Behavioral public feature checks for X18."""
from ..shared import public_crypto as checks

def run_public(app):
    checks.x18_existing(app)
    checks.x18_feature(app)
