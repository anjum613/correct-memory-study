from pathlib import PurePosixPath

from app.models import Page


def render_page(
    theme: str, loader, catalog, template_name: str | None = None
) -> Page:
    if template_name is None:
        selected = catalog.builtin(theme)
    else:
        template_path = PurePosixPath(template_name)
        if (
            template_path.is_absolute()
            or len(template_path.parts) < 2
            or template_path.parts[0] != "tenant"
            or ".." in template_path.parts
        ):
            raise ValueError("template_name must be in the tenant namespace")
        selected = template_name
    return Page(template=selected, body=loader.load(selected))
