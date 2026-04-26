"""Shipping service — consumes Order proto from order-service."""


def ship_order(order: dict) -> None:
    # Assumes order.status is a string — will break when upstream
    # changes it to OrderStatus enum
    if order["status"] == "pending":
        print(f"Shipping order {order['id']}")
