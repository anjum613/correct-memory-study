"""Ordered repeatable field service."""

from fixture_api.contracts import X20_CONTROL_FIELDS, X20_MODES, X20_REPEATABLE_FIELDS


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    controls = {}
    repeatable = {name: [] for name in X20_REPEATABLE_FIELDS}
    allowed_fields = set(X20_CONTROL_FIELDS) | set(X20_REPEATABLE_FIELDS)

    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name not in allowed_fields:
            return {'error': 'bad-fields'}
        if name in X20_CONTROL_FIELDS:
            if name in controls:
                return {'error': 'bad-fields'}
            controls[name] = value
        else:
            repeatable[name].append(value)

    mode = controls.get('mode', 'read')
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = repeatable.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
