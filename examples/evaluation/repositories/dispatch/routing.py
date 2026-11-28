"""Zone labels and availability calculations for a dispatch service."""


def normalize_zone(code: str) -> str:
    """Return an upper-case zone label with hyphen separators."""
    label = code.strip().upper()
    if not label:
        raise ValueError("Zone code is empty")
    return label.replace(" ", "-")


def next_departure(ready_hour: int, departure_hours: list[int]) -> int | None:
    """Return the first departure an order ready at the given hour can catch."""
    if not 0 <= ready_hour < 24 or any(not 0 <= hour < 24 for hour in departure_hours):
        raise ValueError("Hours must be between 0 and 23")
    return min((hour for hour in departure_hours if hour > ready_hour), default=None)
