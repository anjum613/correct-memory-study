def badge(code):
    return f'<span class="status">{int(code)}</span>'

def render_table(rows, *, descending=False):
    raise NotImplementedError('grouped status table')
