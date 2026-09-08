"""Run the fixed child with its existing inherited environment."""


def run(child, parent_environment, caller_overlay):
    return child.run(dict(parent_environment))
