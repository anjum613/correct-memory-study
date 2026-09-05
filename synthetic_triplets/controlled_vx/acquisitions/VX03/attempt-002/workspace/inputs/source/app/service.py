def export_generated(reports, store, *, format_name='text'):
    if format_name not in ('text', 'upper'):
        raise ValueError('unknown format')
    prepared = []
    seen = set()
    for report in reports:
        identifier = report.get('id')
        title, body = report.get('title'), report.get('body')
        if type(identifier) is not int or not isinstance(title, str) or not isinstance(body, str):
            raise ValueError('invalid report')
        name = f'report-{identifier}.txt'
        address = store.address(name)
        if address in seen:
            raise ValueError('duplicate destination')
        seen.add(address)
        document = title + '\n' + body
        if format_name == 'upper':
            document = document.upper()
        prepared.append((name, document))
    paths = [name for name, _ in prepared]
    characters = [len(document) for _, document in prepared]
    store.commit(prepared)
    return {'paths': paths, 'characters': characters,
            'total': sum(characters), 'count': len(prepared)}
