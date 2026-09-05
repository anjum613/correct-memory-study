from app.operations import prepare_report


def export_one(identifier, body, store):
    name = f'report-{identifier}.txt'
    store.commit([(name, body)])
    return name


def export_batch(reports, store, *, format_name='text'):
    if format_name not in ('text', 'upper'):
        raise ValueError('unknown format')
    prepared = []
    seen = set()
    for report in reports:
        name, document = prepare_report(report, format_name)
        address = store.address(name)
        if not address.startswith('/exports/'):
            raise ValueError('destination outside export namespace')
        if address in seen:
            raise ValueError('duplicate destination')
        seen.add(address)
        prepared.append((name, document))
    paths = [name for name, _ in prepared]
    characters = [len(document) for _, document in prepared]
    store.commit(prepared)
    return {
        'paths': paths,
        'characters': characters,
        'total': sum(characters),
        'count': len(prepared),
    }
