"""Deterministic speech presentation for authoritative booking data."""
from datetime import date

ENGINEERING_PREFIX = "Fictional engineering property — "


def booking_readback(items, *, engineering=False):
    if not items:
        raise ValueError("A booking readback requires at least one authoritative item")
    visits = []
    for item in items:
        day = date.fromisoformat(item["day"])
        spoken_day = f"{day.strftime('%A')} {day.day} {day.strftime('%B')} {day.year}"
        address = item["address"]
        if engineering and address.startswith(ENGINEERING_PREFIX):
            address = address.removeprefix(ENGINEERING_PREFIX)
        period = {"MORNING": "in the morning", "AFTERNOON": "in the afternoon"}[item["period"]]
        service = {"service": "boiler service", "cp12": "gas safety check", "combined": "boiler service and gas safety check"}[item["service"]]
        visits.append(f"a {service} at {address} on {spoken_day}, {period}")
    return "That's " + "; and ".join(visits) + ". Shall I book that for you?"
