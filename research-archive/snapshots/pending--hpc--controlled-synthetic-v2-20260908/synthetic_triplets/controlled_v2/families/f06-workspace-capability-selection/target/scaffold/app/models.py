from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    user: str
    default_workspace: str
    grants: frozenset[str]


@dataclass(frozen=True)
class Route:
    workspace: str
