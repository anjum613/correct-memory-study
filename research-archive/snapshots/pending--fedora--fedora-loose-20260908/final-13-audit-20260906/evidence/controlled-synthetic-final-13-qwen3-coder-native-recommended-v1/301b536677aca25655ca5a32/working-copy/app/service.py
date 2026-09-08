"""Multi-occurrence field service with control field policies."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    control_fields = {}
    repeatable_fields = {}
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        # Handle control fields (only single occurrence allowed)
        if name == 'mode':
            if name in control_fields:
                return {'error': 'bad-fields'}
            control_fields[name] = value
        # Handle repeatable fields (multiple occurrences allowed)
        elif name == 'tag':
            if name not in repeatable_fields:
                repeatable_fields[name] = []
            repeatable_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}

    mode = control_fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    tags = repeatable_fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
