from collections.abc import Iterable

from .accounts import Account


def balances(accounts: Iterable[Account]) -> dict[str, int]:
    return {account.name: account.balance for account in accounts}
