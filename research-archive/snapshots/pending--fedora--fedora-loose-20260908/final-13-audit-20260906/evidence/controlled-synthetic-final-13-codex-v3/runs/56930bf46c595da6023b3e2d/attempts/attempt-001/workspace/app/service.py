"""Field service supporting ordered repeatable extension fields."""

from fixture_api import contracts as c


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {}
    repeatable_fields = {}
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name in c.X20_CONTROL_FIELDS:
            if name in control_fields:
                return {'error': 'bad-fields'}
            control_fields[name] = value
            continue
        if name in c.X20_REPEATABLE_FIELDS:
            repeatable_fields.setdefault(name, []).append(value)
            continue
        return {'error': 'bad-fields'}

    mode = control_fields.get('mode', 'read')
    if mode not in c.X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = repeatable_fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
