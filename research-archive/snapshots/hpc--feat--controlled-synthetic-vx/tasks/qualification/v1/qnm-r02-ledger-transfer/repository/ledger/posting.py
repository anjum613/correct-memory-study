from .accounts import Account


def transfer(sender: Account, receiver: Account, amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("amount must be an integer")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if sender.balance < amount:
        raise ValueError("insufficient funds")

    sender.balance -= amount
    sender.balance += amount
