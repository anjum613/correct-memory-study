def export_one(identifier, body, store):
    name = f'report-{identifier}.txt'
    store.commit([(name, body)])
    return name

def export_batch(reports, store, *, format_name='text'):
    raise NotImplementedError('batch exports')
