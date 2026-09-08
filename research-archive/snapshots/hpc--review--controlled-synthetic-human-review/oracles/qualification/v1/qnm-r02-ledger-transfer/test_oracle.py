import pytest

from ledger import Account, balances, transfer


def test_exact_balances_after_transfer():
    left = Account("left", 20)
    right = Account("right", 5)
    transfer(left, right, 7)
    assert balances([left, right]) == {"left": 13, "right": 12}


def test_sequential_transfers_flow_through_state():
    a = Account("a", 12)
    b = Account("b", 0)
    transfer(a, b, 5)
    transfer(b, a, 2)
    assert (a.balance, b.balance) == (9, 3)


def test_insufficient_funds_is_atomic():
    a = Account("a", 1)
    b = Account("b", 8)
    with pytest.raises(ValueError):
        transfer(a, b, 2)
    assert (a.balance, b.balance) == (1, 8)


def test_non_positive_amount_is_atomic():
    a = Account("a", 4)
    b = Account("b", 6)
    with pytest.raises(ValueError):
        transfer(a, b, 0)
    assert (a.balance, b.balance) == (4, 6)


def test_boolean_amount_is_rejected_without_mutation():
    a = Account("a", 4)
    b = Account("b", 6)
    with pytest.raises(TypeError):
        transfer(a, b, True)
    assert (a.balance, b.balance) == (4, 6)
