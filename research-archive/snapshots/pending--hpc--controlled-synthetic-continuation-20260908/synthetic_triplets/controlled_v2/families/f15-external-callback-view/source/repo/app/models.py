from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    secret: str


@dataclass(frozen=True)
class PublicAccount:
    account_id: str
    name: str
