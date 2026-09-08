"""Field service with repeatable extension fields."""

from fixture_api.contracts import X20_CONTROL_FIELDS, X20_REPEATABLE_FIELDS, X20_MODES


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {}
    extension_fields = {}
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
            continue
        if name in X20_REPEATABLE_FIELDS:
            extension_fields.setdefault(name, []).append(value)
            continue
        return {'error': 'bad-fields'}

    mode = control_fields.get('mode', 'read')
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = extension_fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
