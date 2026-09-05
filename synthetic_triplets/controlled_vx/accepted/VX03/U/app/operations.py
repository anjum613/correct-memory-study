"""Implementation helpers for this application."""


def prepare_report(report, format_name):
    """Validate and render a report without changing it or the store."""
    if not isinstance(report, dict):
        raise ValueError('invalid report')
    identifier = report.get('id')
    title, body = report.get('title'), report.get('body')
    if (
        type(identifier) is not int
        or not isinstance(title, str)
        or not isinstance(body, str)
    ):
        raise ValueError('invalid report')
    name = report.get('name', f'report-{identifier}.txt')
    if (
        not isinstance(name, str)
        or not name
        or name.startswith('/')
        or '\x00' in name
        or name.rsplit('/', 1)[-1] in ('', '.', '..')
    ):
        raise ValueError('invalid name')
    document = title + '\n' + body
    if format_name == 'upper':
        document = document.upper()
    return name, document
