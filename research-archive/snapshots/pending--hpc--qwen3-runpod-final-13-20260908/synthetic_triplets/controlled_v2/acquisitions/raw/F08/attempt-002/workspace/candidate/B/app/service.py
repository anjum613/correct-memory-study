from app.models import Badge


def render_badge(code: int, label: str | None = None) -> Badge:
    text = str(code)
    return Badge(html=f'<span class="status">{text}</span>')
