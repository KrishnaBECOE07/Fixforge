"""Packing and restock helpers for a small inventory service."""


def shipment_count(units: int, capacity: int) -> int:
    """Return the number of shipments needed for the given units."""
    if units < 0 or capacity <= 0:
        raise ValueError("Units must be nonnegative and capacity must be positive")
    return units // capacity


def restock_queue(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Return items in descending priority order."""
    return sorted(items, key=lambda item: (item[1], item[0]), reverse=True)
