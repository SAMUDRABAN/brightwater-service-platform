"""Deterministic substantive readback checks for isolated text evaluations."""

import calendar
import re
from datetime import date

from brightwater.policy import now


def spoken_numbers(text):
    units = {
        word: i
        for i, word in enumerate(
            "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
        )
    }
    tens = {
        word: i * 10
        for i, word in enumerate(
            "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()
        )
        if i >= 2
    }
    ordinals = {
        word: i + 1
        for i, word in enumerate(
            "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth twentyfirst twentysecond twentythird twentyfourth twentyfifth twentysixth twentyseventh twentyeighth twentyninth thirtieth thirtyfirst".split()
        )
    }
    text = text.lower().replace("-", " ")
    # Year pairs and digit sequences are concatenation, not cardinal addition.
    # Real phone output said "PO four zero J T" and "twenty twenty six".
    def year_pair(match):
        tail = match.group(1).split()
        value = tens.get(tail[0], units.get(tail[0], 0))
        if len(tail) == 2:
            value += units[tail[1]]
        return str(2000 + value)
    year_tail = "(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    digit = "(?:zero|one|two|three|four|five|six|seven|eight|nine)"
    text = re.sub(r"\btwenty (" + year_tail + r"(?: " + digit + r")?)\b", year_pair, text)
    text = re.sub(r"\b" + digit + r"(?:\s+" + digit + r")+\b",
                  lambda match: "".join(str(units[word]) for word in match.group().split()), text)
    tokens = re.findall(r"[a-z]+|\d+(?:st|nd|rd|th)?|[^a-z\d\s]", text.lower().replace("-", " "))
    result = []
    index = 0
    while index < len(tokens):
        word = tokens[index]
        if word not in units and word not in tens and word not in ordinals:
            result.append(re.sub(r"(st|nd|rd|th)$", "", word) if re.fullmatch(r"\d+(?:st|nd|rd|th)", word) else word)
            index += 1
            continue
        total = current = 0
        while index < len(tokens):
            word = tokens[index]
            if word in units:
                current += units[word]
            elif word in tens:
                current += tens[word]
            elif word in ordinals:
                current += ordinals[word]
            elif word == "hundred":
                current *= 100
            elif word == "thousand":
                total += current * 1000
                current = 0
            elif (
                word == "and"
                and index + 1 < len(tokens)
                and tokens[index + 1] in (units | tens | ordinals)
            ):
                index += 1
                continue
            else:
                break
            index += 1
        result.append(str(total + current))
    return " ".join(result)


def compact(text):
    return re.sub(r"[^a-z0-9]", "", spoken_numbers(text))


def amount_words(number):
    units = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if number < 20:
        return units[number]
    if number < 100:
        return tens[number // 10] + (" " + units[number % 10] if number % 10 else "")
    if number < 1000:
        return (
            units[number // 100]
            + " hundred"
            + (" and " + amount_words(number % 100) if number % 100 else "")
        )
    return str(number)


def ordinal(day):
    return str(day) + (
        "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )


def spoken_address(item):
    address = item["address"]
    prefix = "Fictional engineering property — "
    if item.get("property_id", "").startswith("ENGINEERING-") and address.startswith(prefix):
        return address[len(prefix):]
    return address


def readback_text(proposal):
    names = {
        "service": "boiler service",
        "cp12": "gas safety check",
        "combined": "boiler service and gas safety check",
    }
    parts = []
    for item in proposal.items:
        day = date.fromisoformat(item["day"])
        window = (
            "morning, eight until twelve"
            if item["period"] == "MORNING"
            else "afternoon, twelve until five"
        )
        parts.append(
            f"{spoken_address(item)}, {names[item['service']]}, on {day.strftime('%A')} {ordinal(day.day)} {day.strftime('%B')} {day.year} in the {window}"
        )
    return (
        "Just to confirm: "
        + "; ".join(parts)
        + f". The total is £{proposal.total_pence // 100} including VAT, payable to the engineer. Shall I book that for you?"
    )


def complete_readback(text, proposal):
    """Allow presentation changes, never model-provided claims of completion.

    Deliberately conservative. Multi-property readbacks require all details and
    reject multiple distinct appointment dates/windows (separate proposals).
    """
    lower = spoken_numbers(text)
    if re.search(r"\b(?:not|instead|except|cancel|different|maybe|possibly)\b", lower):
        return False
    full = compact(text)
    for item in proposal.items:
        if compact(spoken_address(item)) not in full:
            return False
        services = {
            "service": ["boiler service"],
            "cp12": ["gas safety check", "cp12", "gas safety certificate"],
            "combined": [
                "boiler service and gas safety check",
                "boiler service and cp12",
                "boiler service and gas safety certificate",
            ],
        }
        if not any(compact(name) in full for name in services[item["service"]]):
            return False
        day = date.fromisoformat(item["day"])
        # If a year is spoken it must be the proposal year. Omitted year is
        # allowed only for an appointment in the current calendar year.
        spoken_years = re.findall(r"\b20\d\d\b", lower)
        if any(int(y) != day.year for y in spoken_years) or (
            not spoken_years and day.year != now().year
        ):
            return False
        date_forms = [
            item["day"],
            f"{ordinal(day.day)} {calendar.month_name[day.month]}",
            f"{day.day} {calendar.month_name[day.month]}",
            f"{calendar.month_name[day.month]} {ordinal(day.day)}",
            f"{day.day} of {calendar.month_name[day.month]}",
            f"{ordinal(day.day)} of {calendar.month_name[day.month]}",
        ]
        if not any(compact(form) in full for form in date_forms):
            return False
        if item["period"] == "MORNING":
            if "morning" not in lower or not any(
                compact(w) in full
                for w in ["eight until twelve", "8am to 12pm", "8am and 12pm", "8 to 12"]
            ):
                return False
        elif "afternoon" not in lower or not any(
            compact(w) in full
            for w in ["twelve until five", "12pm to 5pm", "12pm and 5pm", "12 to 5"]
        ):
            return False
    amount = proposal.total_pence // 100
    currencies = re.findall(r"£\s*(\d+)(?:\.00)?(?!\d)", lower)
    if any(int(value) != amount for value in currencies):
        return False
    price = re.search(rf"(?<![\d]){amount}(?:\.00)?\s*(?:pounds|including vat)\b", lower) or bool(
        currencies
    )
    if not price:
        total = re.search(r"\btotal (?:is|of|comes to) (.+?) (?:including|inclusive of) vat", lower)
        price = bool(
            total and compact(total.group(1).replace("pounds", "")) == compact(amount_words(amount))
        )
    return bool(price and "vat" in lower and "engineer" in lower and "book" in lower)
