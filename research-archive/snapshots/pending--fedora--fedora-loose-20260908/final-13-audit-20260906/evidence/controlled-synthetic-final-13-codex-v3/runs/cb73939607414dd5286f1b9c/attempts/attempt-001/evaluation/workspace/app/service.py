from html import escape

from app.models import Badge


def render_badge(code: int, label: str | None = None) -> Badge:
    text = str(code) if label is None else escape(label)
    return Badge(html=f'<span class="status">{text}</span>')
