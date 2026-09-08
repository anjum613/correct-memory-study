from shipments import Shipment, summarize_shipment


def test_expedited_summary_uses_full_label():
    shipment = Shipment(reference="DX-17", priority="expedited")
    assert summarize_shipment(shipment) == "Shipment DX-17 | Priority: EXPEDITED"


def test_standard_summary_is_unchanged():
    shipment = Shipment(reference="ST-2", priority="standard")
    assert summarize_shipment(shipment) == "Shipment ST-2 | Priority: STANDARD"
