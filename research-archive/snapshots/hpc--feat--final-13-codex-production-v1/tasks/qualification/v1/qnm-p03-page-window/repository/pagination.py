"""Small, dependency-free pagination helpers."""


def page_slice(items, page: int, page_size: int):
    if not isinstance(page, int) or not isinstance(page_size, int):
        raise TypeError("page and page_size must be integers")
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")
    start = page * page_size
    return list(items[start : start + page_size])
