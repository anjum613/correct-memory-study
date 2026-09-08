"""Single-occurrence field service baseline."""


from fixture_api.contracts import X20_CONTROL_FIELDS, X20_REPEATABLE_FIELDS, X20_MODES


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
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
            continue

        if name not in X20_REPEATABLE_FIELDS:
            return {'error': 'bad-fields'}

        if name not in fields:
            fields[name] = [value]
        else:
            fields[name].append(value)

    mode = fields.get('mode', 'read')
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}

    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}

    tags = fields.get('tag', [])

    return field_service.dispatch({'mode': mode, 'tags': tags})
