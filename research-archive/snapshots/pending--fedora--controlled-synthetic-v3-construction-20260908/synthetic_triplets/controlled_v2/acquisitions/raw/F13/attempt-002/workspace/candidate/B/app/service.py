from app.models import Page


def render_page(
    theme: str, loader, catalog, template_name: str | None = None
) -> Page:
    if template_name is not None:
        raise ValueError("tenant templates are not supported")
    selected = catalog.builtin(theme)
    return Page(template=selected, body=loader.load(selected))
