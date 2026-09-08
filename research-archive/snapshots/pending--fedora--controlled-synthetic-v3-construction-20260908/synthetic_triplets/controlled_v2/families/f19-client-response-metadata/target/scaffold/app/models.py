from dataclasses import dataclass, field


@dataclass
class Response:
    headers: dict[str, str] = field(default_factory=dict)
