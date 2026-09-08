"""Authorize only after complete traversal of the restriction response."""

from dataclasses import dataclass


@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int


def run(paginated_policy_service, resource):
    service = paginated_policy_service
    cursor = 0
    seen = []
    pages = 0
    restricted = False

    while True:
        try:
            if cursor in seen:
                return X27Decision('deny', 'incomplete policy traversal', pages)
            seen.append(cursor)
            pages += 1
            response = service.fetch(cursor)
            if response is service.ERROR:
                return X27Decision('deny', 'policy service error', pages)
            if not isinstance(response, (tuple, list)) or len(response) != 2:
                return X27Decision('deny', 'policy service error', pages)
            restrictions, next_cursor = response
            if not isinstance(restrictions, (list, tuple, set, frozenset)):
                return X27Decision('deny', 'policy service error', pages)
            if resource in restrictions:
                restricted = True
            if next_cursor is None:
                break
            cursor = next_cursor
        except Exception:
            return X27Decision('deny', 'policy service error', pages)

    if restricted:
        return X27Decision('deny', 'matching restriction', pages)
    service.grants.append(resource)
    return X27Decision('allow', 'no matching restriction', pages)
