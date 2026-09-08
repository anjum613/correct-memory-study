from dataclasses import dataclass


@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int


def run(paginated_policy_service, resource):
    service = paginated_policy_service
    try:
        page = service.fetch(0)
        if page is service.ERROR:
            return X27Decision('deny', 'policy service error', 1)
        restrictions, next_cursor = page
        if resource in restrictions:
            return X27Decision('deny', 'matching restriction', 1)
        if next_cursor is not None:
            return X27Decision('deny', 'pagination unavailable', 1)
    except Exception:
        return X27Decision('deny', 'policy service error', 1)
    service.grants.append(resource)
    return X27Decision('allow', 'no matching restriction', 1)
