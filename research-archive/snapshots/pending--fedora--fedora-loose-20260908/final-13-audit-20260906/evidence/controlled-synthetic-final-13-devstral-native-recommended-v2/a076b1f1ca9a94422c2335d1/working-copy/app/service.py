"""Single-occurrence field service baseline with extension fields."""

def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    fields = {}
    tags = []
    control_fields = {'mode', 'tag'}
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
            if name == 'mode' and value not in ('read', 'write'):
                return {'error': 'bad-fields'}
        fields[name] = value

    mode = fields.get('mode', 'read')
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Prepare the result with control fields
    result = {'mode': mode, 'tags': tags}
    
    # Add extension fields to the result
    for name, value in fields.items():
        if name not in control_fields:
            result[name] = value
    
    return field_service.dispatch(result)
