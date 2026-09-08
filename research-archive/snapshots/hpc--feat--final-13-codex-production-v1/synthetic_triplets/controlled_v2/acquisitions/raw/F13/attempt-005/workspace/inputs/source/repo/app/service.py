from app.models import Page


def render_builtin(theme: str, loader, catalog) -> Page:
    selected = catalog.builtin(theme)
    return Page(template=selected, body=loader.load(selected))
