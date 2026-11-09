import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
SERVICES = {
    "service": {"name": "Boiler service", "price_pence": 9500, "minutes": 60},
    "cp12": {"name": "Landlord gas safety certificate", "price_pence": 7500, "minutes": 60},
    "combined": {"name": "Boiler service and gas safety certificate", "price_pence": 14500, "minutes": 90},
}
OUTCOMES = (
    "Gas emergency advice", "Do not call", "Urgent callback", "Complaint",
    "Callback requested", "Booked", "Lead", "Serviced elsewhere", "Not interested",
    "Wrong number", "Not available", "Voicemail", "No answer",
)
GAS_ADVICE = (
    "Please call the National Gas Emergency Service on 0800 111 999 now. "
    "Open doors and windows, and don't use electrical switches or flames. "
    "I'll end this call so you can phone them."
)
CO_ADVICE = (
    "Please get everyone out of the property and call the National Gas Emergency "
    "Service on 0800 111 999 now. I'll end this call so you can phone them."
)


class Rejected(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def now() -> datetime:
    return datetime.now(UTC)


def uk_phone(value: str) -> str:
    if not re.fullmatch(r"\+44[1-9]\d{8,9}", value):
        raise Rejected("invalid_destination", "Use a consented UK number in E.164 format", 422)
    if value.startswith(("+447700900", "+441632960")):
        raise Rejected("fictional_destination", "Assessment drama numbers cannot be dialled", 422)
    return value


def time_band(at: datetime) -> str:
    local = at.astimezone(UK)
    minutes = local.hour * 60 + local.minute
    return "morning" if minutes < 720 else "midday" if minutes < 900 else "afternoon" if minutes < 1050 else "evening"


def allowed_time(at: datetime, not_before=None) -> bool:
    if at.tzinfo is None:
        raise ValueError("Policy requires a timezone-aware timestamp")
    local = at.astimezone(UK)
    minute = local.hour * 60 + local.minute
    end = 12 * 60 + 55 if local.weekday() == 5 else 19 * 60 + 25
    start = max(600, not_before.hour * 60 + not_before.minute if not_before else 600)
    return local.weekday() != 6 and start <= minute < end


def next_retry(at: datetime, used_bands: set[str], not_before=None) -> datetime | None:
    earliest = at + timedelta(hours=24)
    for day in range(1, 15):
        local = at.astimezone(UK) + timedelta(days=day)
        for hour, minute in [(10, 30), (12, 15), (16, 0), (18, 15)]:
            candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate >= earliest and allowed_time(candidate, not_before) and time_band(candidate) not in used_bands:
                return candidate.astimezone(UTC)
    return None


def _affirmation_words(utterance: str) -> str:
    words = re.sub(r"[^a-z\s]", "", utterance.lower()).split()
    for _ in range(3):
        if words and words[0] in {"uh", "um", "er", "erm", "oh", "well"}:
            words.pop(0)
        else:
            break
    words = ["yes" if word in {"yeah", "yep", "yup"} else word for word in words]
    for _ in range(len(words)):
        if words[:2] == ["yes", "yes"]:
            words.pop(0)
        else:
            break
    return " ".join(words)


def explicit_yes(utterance: str) -> bool:
    # Whole-utterance agreement only, behind the current completed readback.
    # Repeated assent is normal speech; never extract yes from a correction.
    words = _affirmation_words(utterance)
    approved = {"yes", "yes please", "yes book it", "yes thats correct", "please book that",
        "go ahead", "yes go ahead", "yes please do it", "yes do it", "sure", "yes sure",
        "yes please book it", "yes book it please", "yes go ahead and book it", "yes thats fine"}
    return words in approved or any(words == " ".join([phrase] * n) for phrase in approved for n in (2, 3))


def explicit_opt_out(utterance: str) -> bool:
    """Narrow whole-utterance commands; never infer opt-out from a quotation.

    This backstop is independent of model tool selection. It deliberately does
    not attempt general intent classification. Other wording still uses the
    runtime suppression tool and must be qualified on real conversations.
    """
    if not isinstance(utterance, str):
        return False
    spoken = " ".join(re.sub(r"[^a-z\s]", "", utterance.lower()).split())
    return bool(re.fullmatch(
        r"(?:please )?(?:stop (?:calling|phoning)(?: me| this number)?|"
        r"do not (?:call|phone)(?: me| this number)(?: again)?|"
        r"dont (?:call|phone)(?: me| this number)(?: again)?|"
        r"(?:take|remove) (?:me|this number) (?:off|from) (?:your|the) (?:call |calling )?list)"
        r"(?: please)?(?: thank you| thanks)?", spoken))


def explicit_recording_refusal(utterance: str) -> bool:
    if not isinstance(utterance, str):
        return False
    spoken = " ".join(re.sub(r"[^a-z\s]", "", utterance.lower()).split())
    return bool(re.fullmatch(
        r"(?:please )?(?:stop recording(?: me| this call)?|"
        r"(?:dont|do not) record(?: me| this call)?|"
        r"i (?:dont|do not) (?:consent to recording|want (?:this|the call) recorded))"
        r"(?: please)?(?: thank you| thanks)?", spoken))


def identity_affirmative(utterance: str) -> bool:
    # Hesitation and repeated assent are normal speech, not new instructions.
    # Match the whole remaining utterance; never extract a yes from a denial,
    # proxy statement or quotation. This parser is only used behind the named
    # question/playback/timing gate, never as standalone identity or booking.
    return _affirmation_words(utterance) in {"yes", "yes thats right", "thats right", "correct",
        "yes you are", "yes i am", "yes it is", "yes thats correct", "thats me",
        "yes thats me", "thats me yes", "yes speaking", "speaking"}


def self_identifies(utterance: str, name: str) -> bool:
    """Conservative conversational assertion, not strong authentication.

    A name embedded in a relative's answer is not a self-identification.
    """
    def normalise(value):
        return " ".join(re.sub(r"[^a-z\s]", "", value.lower()).split())

    spoken, expected = normalise(utterance), normalise(name)
    return spoken in {
        "speaking", "yes speaking", "yes thats me", expected,
        f"{expected} speaking", f"this is {expected}", f"its {expected}",
        f"yes its {expected}", f"im {expected}",
        f"i am {expected}", f"my name is {expected}",
        f"yes this is {expected}", f"yes {expected} speaking",
        f"yes i am {expected}", f"yes im {expected}",
    }
