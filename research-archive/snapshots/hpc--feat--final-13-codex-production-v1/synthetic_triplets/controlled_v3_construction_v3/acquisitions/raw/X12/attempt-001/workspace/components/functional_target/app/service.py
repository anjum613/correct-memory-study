"""Apply documented caller options to the fixed child's configuration."""


def run(child, parent_environment, caller_overlay):
    options = ("LOCALE", "DATA", "TUNING")
    environment = {}
    for name in options + ("REQUIRED",):
        if name in parent_environment:
            environment[name] = parent_environment[name]

    for name in options:
        if name in caller_overlay:
            value = caller_overlay[name]
            if not isinstance(value, str):
                raise TypeError("Child options must be strings")
            environment[name] = value

    return child.run(environment)
