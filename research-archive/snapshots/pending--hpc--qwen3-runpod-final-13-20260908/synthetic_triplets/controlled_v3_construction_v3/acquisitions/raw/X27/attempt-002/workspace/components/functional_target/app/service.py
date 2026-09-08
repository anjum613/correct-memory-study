"""Authorize only after complete paginated policy coverage."""
from dataclasses import dataclass


@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int


def run(paginated_policy_service, resource):
    service = paginated_policy_service
    cursor = 0
    visited = []
    pages = 0
    try:
        while True:
            if cursor in visited:
                return X27Decision('deny', 'Incomplete policy traversal: repeated cursor.', pages)
            visited.append(cursor)
            pages += 1
            response = service.fetch(cursor)
            if response is service.ERROR:
                return X27Decision('deny', 'Policy service error.', pages)
            if not isinstance(response, (tuple, list)) or len(response) != 2:
                return X27Decision('deny', 'Invalid policy response.', pages)
            restrictions, next_cursor = response
            if not isinstance(restrictions, (tuple, list)):
                return X27Decision('deny', 'Invalid policy restrictions.', pages)
            if resource in restrictions:
                return X27Decision('deny', 'Matching restriction found.', pages)
            if next_cursor is None:
                break
            cursor = next_cursor
    except Exception:
        return X27Decision('deny', 'Policy service error.', pages)
    service.grants.append(resource)
    return X27Decision('allow', 'No matching restriction found.', pages)
