from app.models import Page


def render_page(
    theme: str, loader, catalog, template_name: str | None = None
) -> Page:
    if template_name is not None and not template_name.startswith("tenant/"):
        raise ValueError("custom templates must be in the tenant namespace")
    selected = template_name if template_name is not None else catalog.builtin(theme)
    return Page(template=selected, body=loader.load(selected))
