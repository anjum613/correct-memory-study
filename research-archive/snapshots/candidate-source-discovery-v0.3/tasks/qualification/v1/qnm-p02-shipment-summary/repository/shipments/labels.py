"""Customer-facing labels for shipment priorities."""


def priority_label(priority: str) -> str:
    labels = {
        "standard": "STANDARD",
        "expedited": "EXPEDITE",
        "overnight": "OVERNIGHT",
    }
    return labels.get(priority, "UNKNOWN")
