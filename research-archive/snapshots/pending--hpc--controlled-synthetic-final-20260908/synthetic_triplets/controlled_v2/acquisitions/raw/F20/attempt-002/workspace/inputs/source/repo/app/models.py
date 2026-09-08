from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RelativeReference:
    value: str

    def __post_init__(self):
        parsed = urlsplit(self.value)
        if parsed.scheme or parsed.netloc:
            raise ValueError("reference must be relative")


@dataclass(frozen=True)
class Session:
    origin: str
    cookie: str


@dataclass(frozen=True)
class FetchResult:
    url: str
    body: str
