"""Implementation helpers for this application."""


def group_status_rows(rows, *, descending=False):
    groups = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid status row')
        code, count = row.get('code'), row.get('count')
        if type(code) is not int or type(count) is not int or count < 0:
            raise ValueError('invalid numeric row')
        label = row.get('label', str(code))
        if not isinstance(label, str):
            raise ValueError('invalid label')
        if code in groups:
            group = groups[code]
            if group['label'] != label:
                raise ValueError('conflicting labels for code')
            group['count'] += count
        else:
            groups[code] = {'code': code, 'label': label, 'count': count}
    return [groups[code] for code in sorted(groups, reverse=descending)]
