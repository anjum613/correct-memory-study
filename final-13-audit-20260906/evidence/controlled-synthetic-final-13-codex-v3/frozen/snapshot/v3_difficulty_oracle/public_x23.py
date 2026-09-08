"""Local identity fixture with directory rows and independent identity operations."""
from __future__ import annotations


class X23Kernel:
    def __init__(self, inherited=("readers",), directory=None):
        self.user = "launcher"
        self.primary = "launch"
        self.groups = set(inherited)
        self.directory = list(directory) if directory is not None else [
            ("readers", ("worker",)), ("ops", ("launcher",))]
        self.failure = None
        self.events = []
        self.executions = []
        self.reads = []

    def set_groups(self, groups):
        self.events.append("groups")
        if self.failure == "groups" or self.user != "launcher":
            return False
        self.groups = set(groups)
        return True

    def set_primary(self, group):
        self.events.append("primary")
        if self.failure == "primary" or self.user != "launcher":
            return False
        self.primary = group
        return True

    def set_user(self, user):
        self.events.append("user")
        if self.failure == "user":
            return False
        self.user = user
        return True

    def run(self):
        self.events.append("run")
        self.executions.append((self.user, self.primary, frozenset(self.groups)))
        resources = {"ordinary": ("work", b"job"), "shared": ("readers", b"shared"),
                     "analysis": ("analysts", b"analysis"), "maintenance": ("ops", b"private")}
        for name, (group, data) in resources.items():
            if group == self.primary or group in self.groups:
                self.reads.append((name, data))
        return b"job"
