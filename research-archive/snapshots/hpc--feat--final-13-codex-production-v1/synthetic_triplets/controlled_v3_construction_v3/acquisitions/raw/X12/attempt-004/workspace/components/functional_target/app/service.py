"""Run the fixed child with only its documented configuration."""


def run(child, parent_environment, caller_overlay):
    supported_options = ("LOCALE", "DATA", "TUNING")
    environment = {
        name: parent_environment[name]
        for name in (*supported_options, "REQUIRED")
        if name in parent_environment
    }
    for name in supported_options:
        if name in caller_overlay:
            value = caller_overlay[name]
            if not isinstance(value, str):
                raise TypeError("Child options must be strings")
            environment[name] = value
    return child.run(environment)
