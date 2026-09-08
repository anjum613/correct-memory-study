"""Behavioral public feature checks for X11."""
from ..shared import public_suite as checks

def run_public(app):
    checks.x11_existing(app)
    checks.x11_feature(app)
