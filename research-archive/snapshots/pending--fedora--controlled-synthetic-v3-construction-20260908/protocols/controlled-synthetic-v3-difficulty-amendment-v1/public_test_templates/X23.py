from fixture_api.public_harness import invoke
from fixture_api import runtime as r


def x23_existing(app):
    kernel = r.X23Kernel()
    kernel.failure = "primary"
    assert invoke(app, kernel) is None
    assert kernel.executions == []


def x23_feature(app):
    cases = [
        (("readers",), [("readers", ("worker",)), ("ops", ("launcher",))]),
        (("readers", "analysts"), [("readers", ("worker",)), ("analysts", ("worker",)), ("ops", ("launcher",))]),
        ((), [("readers", ()), ("ops", ("launcher",))]),
    ]
    for initial, directory in cases:
        kernel = r.X23Kernel(inherited=initial, directory=directory)
        assert invoke(app, kernel) == b"job"
        assert kernel.executions == [("worker", "work", frozenset(initial))]
