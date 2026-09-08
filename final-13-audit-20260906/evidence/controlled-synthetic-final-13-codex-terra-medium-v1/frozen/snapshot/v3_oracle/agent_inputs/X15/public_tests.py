"""Behavioral public feature checks for X15."""
from ..shared import public_crypto as checks

def run_public(app):
    checks.x15_existing(app)
    checks.x15_feature(app)
