from app.models import Badge


def render_code(code: int) -> Badge:
    text = str(code)
    return Badge(html=f'<span class="status">{text}</span>')
