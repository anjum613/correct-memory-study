"""Run the fixed child using inherited configuration only."""


def run(child, parent_environment, caller_overlay):
    return child.run(dict(parent_environment))
