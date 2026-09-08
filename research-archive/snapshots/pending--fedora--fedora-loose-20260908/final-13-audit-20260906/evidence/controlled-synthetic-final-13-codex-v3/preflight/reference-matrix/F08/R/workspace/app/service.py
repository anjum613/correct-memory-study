import html

from app.models import Badge


def render_badge(code: int, label: str | None = None) -> Badge:
    text = str(code) if label is None else label
    safe_text = html.escape(text)
    return Badge(html=f'<span class="status">{safe_text}</span>')
