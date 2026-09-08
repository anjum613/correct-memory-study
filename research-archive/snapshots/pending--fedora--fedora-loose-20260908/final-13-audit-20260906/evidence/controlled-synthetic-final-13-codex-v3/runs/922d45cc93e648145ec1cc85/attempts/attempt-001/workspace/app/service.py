"""Field service with ordered repeatable extension fields."""

from fixture_api.contracts import X20_CONTROL_FIELDS, X20_REPEATABLE_FIELDS, X20_MODES


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    repeatable_fields = {name: [] for name in X20_REPEATABLE_FIELDS}
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name in X20_CONTROL_FIELDS:
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
        elif name in X20_REPEATABLE_FIELDS:
            repeatable_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}

    mode = fields.get('mode', X20_MODES[0])
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = repeatable_fields['tag']
    return field_service.dispatch({'mode': mode, 'tags': tags})
