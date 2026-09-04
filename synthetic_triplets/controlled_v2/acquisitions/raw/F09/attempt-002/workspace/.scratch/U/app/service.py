from app.models import Reservation


def reserve_one(name: str, owner: str, registry) -> Reservation:
    if registry.exists(name):
        raise ValueError("name is already reserved")
    registry.put(name, owner)
    return Reservation(name=name, owner=owner)


def reserve_batch(requests, registry, scheduler) -> list[Reservation]:
    phases = []
    for name, owner in requests:
        def check(name=name):
            if registry.exists(name):
                raise ValueError("name is already reserved")

        def commit(name=name, owner=owner):
            registry.put(name, owner)
            return Reservation(name=name, owner=owner)

        phases.append((check, commit))

    return scheduler.run_phased(phases)
