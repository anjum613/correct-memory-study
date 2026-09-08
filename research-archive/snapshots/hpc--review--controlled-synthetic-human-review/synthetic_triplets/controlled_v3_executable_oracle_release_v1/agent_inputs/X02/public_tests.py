"""Behavioral public feature checks for X02."""
from ..shared import x02_public as checks

def run_public(app):
    checks.x02_existing(app)
    checks.x02_feature(app)
