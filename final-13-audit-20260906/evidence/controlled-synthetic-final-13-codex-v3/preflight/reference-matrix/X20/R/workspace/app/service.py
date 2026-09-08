"""Parse and authorize one unambiguous interpretation before dispatch."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    mode = 'read'
    mode_seen = False
    tags = []
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name == 'mode':
            # Control fields cannot be combined; even equal repeats are invalid.
            if mode_seen or value not in ('read', 'write'):
                return {'error': 'bad-fields'}
            mode = value
            mode_seen = True
        elif name == 'tag':
            tags.append(value)
        else:
            return {'error': 'bad-fields'}

    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    return field_service.dispatch({'mode': mode, 'tags': tags})
