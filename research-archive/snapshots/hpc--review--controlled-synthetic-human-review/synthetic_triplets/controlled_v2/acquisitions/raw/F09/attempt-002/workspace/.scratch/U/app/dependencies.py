from app.models import Reservation


class Registry:
    def __init__(self):
        self.claims = {}

    def exists(self, name):
        return name in self.claims

    def put(self, name, owner):
        self.claims[name] = owner

    def reserve_atomic(self, name, owner):
        if self.exists(name):
            raise ValueError("name is already reserved")
        self.put(name, owner)
        return Reservation(name=name, owner=owner)


class DeterministicScheduler:
    def run_phased(self, phases):
        for check, _commit in phases:
            check()
        return [commit() for _check, commit in phases]

    def run_atomic(self, operations):
        return [operation() for operation in operations]
