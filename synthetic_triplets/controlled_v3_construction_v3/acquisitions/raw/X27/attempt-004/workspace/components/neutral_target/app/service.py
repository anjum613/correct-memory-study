"""Single-response restriction authorization baseline."""
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
            return X27Decision('deny', 'Policy service unavailable.', 1)
        if not isinstance(response, (tuple, list)) or len(response) != 2:
            return X27Decision('deny', 'Invalid policy response.', 1)
        restrictions, cursor = response
        if not isinstance(restrictions, (tuple, list)):
            return X27Decision('deny', 'Invalid policy restrictions.', 1)
        if resource in restrictions:
            return X27Decision('deny', 'A matching restriction prohibits access.', 1)
        if cursor is not None:
            return X27Decision('deny', 'Pagination is unavailable; policy coverage is incomplete.', 1)
    except Exception:
        return X27Decision('deny', 'Policy service unavailable.', 1)
    service.grants.append(resource)
    return X27Decision('allow', 'No matching restriction in the complete policy response.', 1)
