"""Single-occurrence field service baseline."""

from fixture_api import contracts as c


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {field_name: None for field_name in c.X20_CONTROL_FIELDS}
    extension_fields = {field_name: [] for field_name in c.X20_REPEATABLE_FIELDS}

    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name in control_fields:
            if control_fields[name] is not None:
                return {'error': 'bad-fields'}
            control_fields[name] = value
        elif name in extension_fields:
            extension_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}

    mode = control_fields['mode'] if control_fields['mode'] is not None else 'read'
    if mode not in c.X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}

    return field_service.dispatch({'mode': mode, 'tags': extension_fields['tag']})
