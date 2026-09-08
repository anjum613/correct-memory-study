"""Ordered field service with repeatable extension fields."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    tags = []
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name not in ('mode', 'tag'):
            return {'error': 'bad-fields'}
        if name == 'mode':
            # Control fields are single-occurrence: do not combine them.
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
        else:
            # Extension fields are repeatable and retain wire order.
            tags.append(value)

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    return field_service.dispatch({'mode': mode, 'tags': tags})
