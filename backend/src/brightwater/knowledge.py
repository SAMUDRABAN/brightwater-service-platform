"""Versioned public business facts. Customer facts come only from scoped live tools."""

import re

from brightwater.config import settings
from brightwater.policy import SERVICES

VERSION = "assessment-2026-11-04-v1"
DOCUMENTS = [
    ("company", {"company", "business", "based", "address", "location", "portsmouth"},
     "Brightwater Plumbing & Heating Ltd, established 2011; Unit 4, Harbour Trade Park, Portsmouth, PO3 5XX. This is the fictional assessment business."),
    ("office", {"office", "hours", "open", "contact", "sarah", "phone", "number", "callback"},
     "Sarah Collins handles office follow-up Monday-Friday, 08:30-16:00 UK local time. Do not promise an immediate callback or an out-of-hours response."),
    ("arrival", {"arrival", "time", "morning", "afternoon", "appointment", "text", "sms", "window"},
     "Visits use morning 08:00-12:00 or afternoon 12:00-17:00 arrival windows. The business texts the evening before with a two-hour arrival time. Do not promise an exact arrival time now."),
    ("payment", {"pay", "payment", "vat", "cost", "price", "prices", "charge", "discount"},
     "Approved prices include VAT; payment is collected by the engineer on the day. Never collect payment, offer discretionary discounts or quote other work. Quote approved prices only when asked."),
    ("engineers", {"engineer", "engineers", "registered", "gas", "dan", "priya", "tom"},
     "Dan Hughes and Priya Shah are Gas Safe engineers and can do services/certificates. Tom Barker is a plumber and must not be assigned gas work. Availability must come from the live diary."),
    ("landlords", {"landlord", "landlords", "tenant", "tenants", "properties", "access", "certificate", "cp12"},
     "Collect a tenant name and telephone number for every landlord property before booking. Never call tenants. Prefer the same day where live capacity permits; do not invent capacity or certificate-renewal policy."),
    ("escalation", {"complaint", "mark", "quote", "replacement", "other", "work", "problem"},
     "Mark handles complaints. Sarah handles callback requests and other-work quote leads. No diagnosis or quotation for other work is authorised. Gas/CO emergencies must use the immediate safety path, without waiting for knowledge search."),
]


def lookup(query: str):
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    matches = sorted(((len(words & terms), key, text) for key, terms, text in DOCUMENTS),
                     key=lambda row: -row[0])
    answers = [{"id": key, "text": text, "source": VERSION} for score, key, text in matches if score][:3]
    result = {"source_version": VERSION, "scope": "public business facts only", "answers": answers,
              "fallback": None if answers else "No approved answer found. Offer Sarah's help; do not invent an answer."}
    if any(a["id"] == "payment" for a in answers):
        result["approved_services"] = SERVICES
        result["cp12_rate_for_three_or_more_pence"] = 6000
    if any(a["id"] == "office" for a in answers):
        result["office_callback_number"] = settings().office_callback_number or None
    return result
