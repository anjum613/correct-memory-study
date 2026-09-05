from app.operations import group_status_rows
from app.runtime import TABLE_START, TABLE_END


def badge(code):
    return f'<span class="status">{int(code)}</span>'


def render_table(rows, *, descending=False):
    groups = group_status_rows(rows, descending=descending)
    fragments = [TABLE_START]
    total = 0
    for group in groups:
        code, label, count = group['code'], group['label'], group['count']
        fragments.append(f'<tr><td>{code}</td><td>{label}</td><td>{count}</td></tr>')
        total += count
    fragments.append(TABLE_END)
    return {'html': ''.join(fragments), 'total': total, 'groups': groups}
