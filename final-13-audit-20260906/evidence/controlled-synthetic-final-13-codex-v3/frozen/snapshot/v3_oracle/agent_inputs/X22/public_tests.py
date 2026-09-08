"""Behavioral public feature checks for X22."""
from ..shared import public_crypto as checks

def run_public(app):
    checks.x22_existing(app)
    checks.x22_feature(app)
