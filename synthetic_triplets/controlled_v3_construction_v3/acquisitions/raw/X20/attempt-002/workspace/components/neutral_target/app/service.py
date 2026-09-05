"""Single-occurrence field service baseline."""


def run(field_service, principal, ordered_fields):
    fields = {}
    try:
        for field in ordered_fields:
            if not isinstance(field, (tuple, list)) or len(field) != 2:
                return {'error': 'invalid'}
            name, value = field
            if not isinstance(name, str) or not isinstance(value, str):
                return {'error': 'invalid'}
            if name in fields:
                return {'error': 'invalid'}
            fields[name] = value
    except TypeError:
        return {'error': 'invalid'}

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'invalid'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'denied'}
    tags = [fields['tag']] if 'tag' in fields else []
    return field_service.dispatch({'mode': mode, 'tags': tags})
