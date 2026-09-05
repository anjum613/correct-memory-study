"""Interpret ordered fields once before authorization and dispatch."""


def run(field_service, principal, ordered_fields):
    mode = 'read'
    seen_mode = False
    tags = []
    try:
        for field in ordered_fields:
            if not isinstance(field, (tuple, list)) or len(field) != 2:
                return {'error': 'invalid'}
            name, value = field
            if not isinstance(name, str) or not isinstance(value, str):
                return {'error': 'invalid'}
            if name == 'mode':
                if seen_mode or value not in ('read', 'write'):
                    return {'error': 'invalid'}
                seen_mode = True
                mode = value
            elif name == 'tag':
                tags.append(value)
    except TypeError:
        return {'error': 'invalid'}

    parsed = {'mode': mode, 'tags': tags}
    if parsed['mode'] == 'write' and principal != 'writer':
        return {'error': 'denied'}
    return field_service.dispatch(parsed)
