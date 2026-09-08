from dataclasses import dataclass


@dataclass(frozen=True)
class RenderRequest:
    slot_id: str
