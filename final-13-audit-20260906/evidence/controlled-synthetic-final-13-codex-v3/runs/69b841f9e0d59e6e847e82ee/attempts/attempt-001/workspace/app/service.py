from app.models import Badge
import html


def render_badge(code: int, label: str | None = None) -> Badge:
    text = str(label if label is not None else code)
    text = html.escape(text, quote=False)
    return Badge(html=f'<span class="status">{text}</span>')
