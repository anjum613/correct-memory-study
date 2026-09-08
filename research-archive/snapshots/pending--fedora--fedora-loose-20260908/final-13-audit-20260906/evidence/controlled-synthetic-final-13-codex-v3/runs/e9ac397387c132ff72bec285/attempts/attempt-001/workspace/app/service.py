"""Single-occurrence field service baseline."""


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
        if name not in ('mode', 'tag') or name in fields:
            return {'error': 'bad-fields'}
        fields[name] = value

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = [fields['tag']] if 'tag' in fields else []
    return field_service.dispatch({'mode': mode, 'tags': tags})
