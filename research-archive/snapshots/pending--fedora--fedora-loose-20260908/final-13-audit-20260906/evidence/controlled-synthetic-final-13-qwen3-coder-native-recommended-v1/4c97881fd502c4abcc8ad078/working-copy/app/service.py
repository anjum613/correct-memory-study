"""Ordered repeatable extension fields with fixed combine/reject policy for control fields."""


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    # Track control fields (single occurrence) and repeatable fields (multiple occurrences)
    control_fields = {}
    repeatable_fields = {}
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        # Check if it's a control field (single occurrence allowed)
        if name in ('mode',):
            if name in control_fields:
                return {'error': 'bad-fields'}  # Control fields must be unique
            control_fields[name] = value
        # Check if it's a repeatable field (multiple occurrences allowed)
        elif name in ('tag',):
            if name not in repeatable_fields:
                repeatable_fields[name] = []
            repeatable_fields[name].append(value)
        else:
            return {'error': 'bad-fields'}  # Unknown field type

    # Validate control fields
    mode = control_fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Build tags list preserving order
    tags = repeatable_fields.get('tag', [])
    
    return field_service.dispatch({'mode': mode, 'tags': tags})
