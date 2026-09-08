from html import escape

from app.models import Badge


def render_badge(code: int, label: str | None = None) -> Badge:
    text = escape(label if label is not None else str(code))
    return Badge(html=f'<span class="status">{text}</span>')
