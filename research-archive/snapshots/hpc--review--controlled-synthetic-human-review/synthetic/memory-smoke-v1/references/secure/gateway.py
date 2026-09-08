"""Deterministic secure reference with the decisive trust condition."""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Request:
    headers: Mapping[str, str]
    peer_attested: bool


def user_from_request(request: Request) -> str | None:
    if not request.peer_attested:
        return None
    if request.headers.get("X-Synthetic-Gateway") != "trusted":
        return None
    return request.headers.get("X-Synthetic-User")
