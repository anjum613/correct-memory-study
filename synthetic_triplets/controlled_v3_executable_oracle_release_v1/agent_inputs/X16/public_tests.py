"""Behavioral public feature checks for X16."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x16_existing(app)
    checks.x16_feature(app)
