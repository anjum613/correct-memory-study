"""Field service with ordered repeatable fields and fixed control field policy."""

from fixture_api.contracts import X20_CONTROL_FIELDS, X20_REPEATABLE_FIELDS


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    repeatable = {}
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        # Check if it's a control field (must be unique)
        if name in X20_CONTROL_FIELDS:
            if name in fields:
                return {'error': 'bad-fields'}
            fields[name] = value
        # Check if it's a repeatable field
        elif name in X20_REPEATABLE_FIELDS:
            if name not in repeatable:
                repeatable[name] = []
            repeatable[name].append(value)
        # Unknown field
        else:
            return {'error': 'bad-fields'}

    # Validate control fields
    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Collect all tags in order
    tags = repeatable.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
