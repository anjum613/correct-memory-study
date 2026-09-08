from app.models import Badge


def render_badge(code: int, label: str | None = None) -> Badge:
    if label is not None:
        text = label
    else:
        text = str(code)
    return Badge(html=f'<span class="status">{text}</span>')
