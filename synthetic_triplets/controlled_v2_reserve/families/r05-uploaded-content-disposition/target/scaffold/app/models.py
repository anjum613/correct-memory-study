from dataclasses import dataclass


@dataclass(frozen=True)
class Response:
    headers: dict
    body: bytes
