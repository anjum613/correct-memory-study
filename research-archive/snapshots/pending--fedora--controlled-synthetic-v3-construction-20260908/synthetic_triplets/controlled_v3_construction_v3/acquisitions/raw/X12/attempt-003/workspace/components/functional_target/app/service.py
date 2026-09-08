"""Run the fixed child with its documented configuration options."""


def run(child, parent_environment, caller_overlay):
    environment = {}
    for name in ('LOCALE', 'DATA', 'TUNING'):
        if name in caller_overlay:
            value = caller_overlay[name]
        else:
            value = parent_environment[name]
        if not isinstance(value, str):
            raise TypeError(name + ' must be a string')
        environment[name] = value
    environment['REQUIRED'] = parent_environment['REQUIRED']
    return child.run(environment)
