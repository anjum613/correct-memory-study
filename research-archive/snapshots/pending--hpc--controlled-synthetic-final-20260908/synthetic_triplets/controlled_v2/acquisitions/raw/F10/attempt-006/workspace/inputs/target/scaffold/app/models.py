from dataclasses import dataclass


@dataclass(frozen=True)
class HttpResponse:
    url: str
    body: str
