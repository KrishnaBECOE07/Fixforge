"""Small standard-library scheduling helpers for the FixForge pilot."""


def slots_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    """Return whether two half-open meeting intervals overlap."""
    first_start, first_end = first
    second_start, second_end = second
    return first_start <= second_end and second_start <= first_end


def billable_minutes(minutes: int, increment: int = 15) -> int:
    """Round a nonnegative duration up to the next billing increment."""
    if minutes < 0 or increment < 1:
        raise ValueError("Duration and increment must be valid")
    return (minutes // increment + 1) * increment


def unique_guests(addresses: list[str]) -> list[str]:
    """Return address spellings in first-seen order, ignoring case for duplicates."""
    return list(dict.fromkeys(addresses))
