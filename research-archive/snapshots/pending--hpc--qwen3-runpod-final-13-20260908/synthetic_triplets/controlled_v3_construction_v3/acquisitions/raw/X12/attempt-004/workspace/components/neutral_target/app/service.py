"""Run the fixed child with inherited configuration only."""


def run(child, parent_environment, caller_overlay):
    return child.run(dict(parent_environment))
