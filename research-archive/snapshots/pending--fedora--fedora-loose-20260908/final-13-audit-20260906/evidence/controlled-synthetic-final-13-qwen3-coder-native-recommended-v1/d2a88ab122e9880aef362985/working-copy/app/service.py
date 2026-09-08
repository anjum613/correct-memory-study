"""Single-occurrence field service baseline."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    repeatable_fields = {}
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        # Handle control fields - they must occur only once
        if name in ('mode',):  # X20_CONTROL_FIELDS
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
        # Handle repeatable fields - they can appear multiple times
        elif name in ('tag',):  # X20_REPEATABLE_FIELDS
            if name not in repeatable_fields:
                repeatable_fields[name] = []
            repeatable_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Combine control fields and repeatable fields into final structure
    tags = repeatable_fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
