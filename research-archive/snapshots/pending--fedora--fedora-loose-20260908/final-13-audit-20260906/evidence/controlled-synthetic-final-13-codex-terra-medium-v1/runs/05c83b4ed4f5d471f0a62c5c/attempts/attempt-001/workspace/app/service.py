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
        if name not in ('mode', 'tag'):
            return {'error': 'bad-fields'}
        # Control fields have a single, unambiguous value.  Extension fields
        # are repeatable and must retain their supplied order.
        if name == 'mode':
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
        else:
            fields.setdefault(name, []).append(value)

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
