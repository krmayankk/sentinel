"""Order service handler — uses the proto definition."""

def create_order(customer_id: str, items: list) -> dict:
    return {
        "customer_id": customer_id,
        "items": items,
        "status": "ORDER_STATUS_PENDING",
        "tracking_id": "",
    }
