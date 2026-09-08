"""Ordered repeatable extension field service."""

from fixture_api.contracts import X20_CONTROL_FIELDS, X20_MODES, X20_REPEATABLE_FIELDS


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {}
    repeatable_fields = {name: [] for name in X20_REPEATABLE_FIELDS}
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name in X20_CONTROL_FIELDS:
            if name in control_fields:
                return {'error': 'bad-fields'}
            control_fields[name] = value
        elif name in X20_REPEATABLE_FIELDS:
            repeatable_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}

    mode = control_fields.get('mode', 'read')
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = repeatable_fields['tag']
    return field_service.dispatch({'mode': mode, 'tags': tags})
