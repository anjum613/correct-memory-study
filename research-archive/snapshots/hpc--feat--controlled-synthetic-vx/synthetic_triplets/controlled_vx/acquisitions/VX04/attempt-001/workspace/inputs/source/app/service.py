def render_numeric_table(rows, *, descending=False):
    counts = {}
    for row in rows:
        code, count = row.get('code'), row.get('count')
        if type(code) is not int or type(count) is not int or count < 0:
            raise ValueError('invalid numeric row')
        counts[code] = counts.get(code, 0) + count
    groups = []
    fragments = ['<table class="status"><tbody>']
    total = 0
    for code in sorted(counts, reverse=descending):
        count = counts[code]
        label = str(code)
        groups.append({'code': code, 'label': label, 'count': count})
        fragments.append(f'<tr><td>{code}</td><td>{label}</td><td>{count}</td></tr>')
        total += count
    fragments.append('</tbody></table>')
    return {'html': ''.join(fragments), 'total': total, 'groups': groups}
