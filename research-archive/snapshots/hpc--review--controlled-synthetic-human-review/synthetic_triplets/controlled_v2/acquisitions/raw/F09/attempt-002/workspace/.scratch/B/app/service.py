from app.models import Reservation


def reserve_one(name: str, owner: str, registry) -> Reservation:
    if registry.exists(name):
        raise ValueError("name is already reserved")
    registry.put(name, owner)
    return Reservation(name=name, owner=owner)


def reserve_batch(requests, registry, scheduler) -> list[Reservation]:
    raise NotImplementedError("batch reservation is not implemented")
