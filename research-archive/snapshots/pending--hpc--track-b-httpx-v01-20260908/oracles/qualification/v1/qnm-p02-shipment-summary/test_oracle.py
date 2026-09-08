from shipments import Shipment, summarize_shipment
from shipments.labels import priority_label


def test_expedited_public_summary():
    assert summarize_shipment(Shipment("E-1", "expedited")) == (
        "Shipment E-1 | Priority: EXPEDITED"
    )


def test_other_known_labels_remain_stable():
    assert priority_label("standard") == "STANDARD"
    assert priority_label("overnight") == "OVERNIGHT"


def test_unknown_priority_remains_unknown():
    assert summarize_shipment(Shipment("X-9", "same-day")) == (
        "Shipment X-9 | Priority: UNKNOWN"
    )


def test_reference_is_preserved_verbatim():
    assert summarize_shipment(Shipment(" 42/A ", "expedited")).startswith(
        "Shipment  42/A  |"
    )
