from ledger import Account, balances, transfer


def test_transfer_moves_funds_between_accounts():
    sender = Account("sender", 10)
    receiver = Account("receiver", 2)
    transfer(sender, receiver, 4)
    assert balances([sender, receiver]) == {"sender": 6, "receiver": 6}


def test_total_balance_is_conserved():
    sender = Account("sender", 9)
    receiver = Account("receiver", 1)
    transfer(sender, receiver, 3)
    assert sender.balance + receiver.balance == 10
