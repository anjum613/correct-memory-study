from app.models import Reservation


def reserve_startup(name: str, owner: str, registry) -> Reservation:
    if registry.exists(name):
        raise ValueError("name is already reserved")
    registry.put(name, owner)
    return Reservation(name=name, owner=owner)
