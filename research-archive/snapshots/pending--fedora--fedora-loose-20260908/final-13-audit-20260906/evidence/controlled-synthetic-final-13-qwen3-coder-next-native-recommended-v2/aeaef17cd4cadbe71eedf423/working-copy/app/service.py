"""Single-occurrence field service baseline."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    tags = []
    mode = None
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name == 'mode':
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
            mode = value
        elif name == 'tag':
            tags.append(value)
        else:
            return {'error': 'bad-fields'}

    effective_mode = mode if mode is not None else 'read'
    if effective_mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if effective_mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    return field_service.dispatch({'mode': effective_mode, 'tags': tags})
