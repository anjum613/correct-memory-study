from .labels import priority_label
from .models import Shipment


def summarize_shipment(shipment: Shipment) -> str:
    return f"Shipment {shipment.reference} | Priority: {priority_label(shipment.priority)}"
