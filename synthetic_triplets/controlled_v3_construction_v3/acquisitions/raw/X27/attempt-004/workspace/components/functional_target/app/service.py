"""Authorize only after establishing complete restriction coverage."""
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
    restricted = False
    try:
        while True:
            if cursor in visited:
                return X27Decision(
                    'deny', 'Policy pagination cycle; policy coverage is incomplete.', pages
                )
            visited.append(cursor)
            pages += 1
            response = service.fetch(cursor)
            if response is service.ERROR:
                return X27Decision('deny', 'Policy service unavailable.', pages)
            if not isinstance(response, (tuple, list)) or len(response) != 2:
                return X27Decision('deny', 'Invalid policy response.', pages)
            restrictions, next_cursor = response
            if not isinstance(restrictions, (tuple, list)):
                return X27Decision('deny', 'Invalid policy restrictions.', pages)
            if resource in restrictions:
                restricted = True
            if next_cursor is None:
                break
            cursor = next_cursor
    except Exception:
        return X27Decision('deny', 'Policy service unavailable.', pages)
    if restricted:
        return X27Decision('deny', 'A matching restriction prohibits access.', pages)
    service.grants.append(resource)
    return X27Decision(
        'allow', 'No matching restriction in the complete policy response.', pages
    )
