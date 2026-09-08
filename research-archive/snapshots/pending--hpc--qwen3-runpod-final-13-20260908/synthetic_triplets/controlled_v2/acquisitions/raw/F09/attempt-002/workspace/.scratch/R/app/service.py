from app.models import Reservation


def reserve_one(name: str, owner: str, registry) -> Reservation:
    if registry.exists(name):
        raise ValueError("name is already reserved")
    registry.put(name, owner)
    return Reservation(name=name, owner=owner)


def reserve_batch(requests, registry, scheduler) -> list[Reservation]:
    operations = [
        lambda name=name, owner=owner: registry.reserve_atomic(name, owner)
        for name, owner in requests
    ]
    return scheduler.run_atomic(operations)
