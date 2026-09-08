"""Single-page policy authorization baseline."""
from dataclasses import dataclass


@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int


def run(paginated_policy_service, resource):
    service = paginated_policy_service
    try:
        response = service.fetch(0)
        if response is service.ERROR:
            return X27Decision('deny', 'Policy service error.', 1)
        if not isinstance(response, (tuple, list)) or len(response) != 2:
            return X27Decision('deny', 'Invalid policy response.', 1)
        restrictions, next_cursor = response
        if not isinstance(restrictions, (tuple, list)):
            return X27Decision('deny', 'Invalid policy restrictions.', 1)
        if resource in restrictions:
            return X27Decision('deny', 'Matching restriction found.', 1)
        if next_cursor is not None:
            return X27Decision('deny', 'Policy pagination is unavailable.', 1)
    except Exception:
        return X27Decision('deny', 'Policy service error.', 1)
    service.grants.append(resource)
    return X27Decision('allow', 'No matching restriction found.', 1)
