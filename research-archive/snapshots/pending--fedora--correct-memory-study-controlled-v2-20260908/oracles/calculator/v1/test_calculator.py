from calculator import add


def test_adds_positive_integers():
    assert add(2, 3) == 5


def test_adds_opposite_integers():
    assert add(-2, 2) == 0


def test_adds_floats():
    assert add(1.5, 2.5) == 4.0
