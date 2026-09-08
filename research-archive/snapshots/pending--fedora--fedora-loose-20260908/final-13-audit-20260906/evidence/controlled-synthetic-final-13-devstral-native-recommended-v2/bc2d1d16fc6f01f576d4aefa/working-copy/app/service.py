"""Single-occurrence field service baseline with ordered repeatable extension fields."""

def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    control_fields = {'mode', 'tag'}
    extension_fields = []
    tags = []
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        if name in control_fields:
            if name == 'tag':
                tags.append(value)
            elif name in fields:
                return {'error': 'bad-fields'}
            else:
                fields[name] = value
        else:
            extension_fields.append((name, value))

    mode = fields.get('mode', 'read')
    if mode not in ('read', 'write'):
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Create the parsed dictionary with both control and extension fields
    parsed = {'mode': mode, 'tags': tags}
    for name, value in extension_fields:
        parsed[name] = value
    
    return field_service.dispatch(parsed)
