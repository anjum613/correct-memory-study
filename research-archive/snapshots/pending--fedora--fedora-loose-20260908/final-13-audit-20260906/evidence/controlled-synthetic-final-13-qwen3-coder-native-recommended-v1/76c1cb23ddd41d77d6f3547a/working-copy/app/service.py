"""Single-occurrence field service baseline with support for ordered repeatable fields."""
from fixture_api.contracts import X20_CONTROL_FIELDS, X20_REPEATABLE_FIELDS, X20_MODES


def run(field_service, principal, ordered_fields):
    if not isinstance(ordered_fields, (list, tuple)):
        return {'error': 'bad-fields'}

    # Separate control fields (single occurrence) from repeatable fields (multiple occurrence)
    control_fields = {}
    repeatable_fields = {field_name: [] for field_name in X20_REPEATABLE_FIELDS}
    
    for field in ordered_fields:
        if not isinstance(field, (list, tuple)) or len(field) != 2:
            return {'error': 'bad-fields'}
        name, value = field
        if not isinstance(name, str) or not isinstance(value, str):
            return {'error': 'bad-fields'}
        
        # Check if field name is valid
        if name not in X20_CONTROL_FIELDS and name not in X20_REPEATABLE_FIELDS:
            return {'error': 'bad-fields'}
            
        # Handle control fields (single occurrence, first value wins)
        if name in X20_CONTROL_FIELDS:
            if name not in control_fields:
                control_fields[name] = value
        # Handle repeatable fields (multiple occurrences, preserve order)
        elif name in X20_REPEATABLE_FIELDS:
            repeatable_fields[name].append(value)
    
    # Validate control fields
    mode = control_fields.get('mode', 'read')
    if mode not in X20_MODES:
        return {'error': 'bad-fields'}
    if mode == 'write' and principal != 'writer':
        return {'error': 'forbidden'}
    
    # Prepare final structure
    tags = repeatable_fields.get('tag', [])
    return field_service.dispatch({'mode': mode, 'tags': tags})
