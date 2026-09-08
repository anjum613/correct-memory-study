from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    asset_id: str
    owner: str
    body: str
