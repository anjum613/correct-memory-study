import pytest

from dependency_order import installation_order


def test_chain_places_every_dependency_first():
    graph = {"web": ("api",), "api": ("db",), "db": ()}
    assert installation_order(graph) == ["db", "api", "web"]


def test_shared_dependency_appears_once():
    graph = {"left": ("core",), "right": ("core",), "core": ()}
    order = installation_order(graph)
    assert order.count("core") == 1
    assert order.index("core") < order.index("left")
    assert order.index("core") < order.index("right")


def test_dependency_absent_from_top_level_is_included():
    assert installation_order({"app": ("runtime",)}) == ["runtime", "app"]


def test_empty_graph_is_empty():
    assert installation_order({}) == []


def test_long_cycle_is_rejected():
    with pytest.raises(ValueError):
        installation_order({"a": ("b",), "b": ("c",), "c": ("a",)})
