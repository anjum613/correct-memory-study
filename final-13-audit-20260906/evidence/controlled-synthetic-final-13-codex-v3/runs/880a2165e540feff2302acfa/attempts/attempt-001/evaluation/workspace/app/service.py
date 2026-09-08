"""Field service with ordered repeatable extension handling."""

from fixture_api import contracts as c


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {}
    extension_fields = {}

    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        if name in control_fields and name in c.X20_CONTROL_FIELDS:
            return {'error': 'bad-fields'}
        if name in c.X20_CONTROL_FIELDS:
            control_fields[name] = value
            continue
        if (
            name not in c.X20_REPEATABLE_FIELDS
            and name in extension_fields
        ):
            return {'error': 'bad-fields'}
        extension_fields.setdefault(name, []).append(value)

    mode = control_fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    tags = list(extension_fields.get('tag', ()))
    return field_service.dispatch({'mode': mode, 'tags': tags})
